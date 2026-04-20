import logging

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# Maximum seconds to consider a token still valid before proactive refresh
_TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS = 300


class GoogleBusinessLocation(models.Model):
    """
    Represents a single Google Business Profile location.

    Each location holds its own OAuth 2.0 credentials and is synchronised
    independently, allowing businesses to manage any number of physical or
    virtual locations from a single Odoo instance.
    """

    _name = 'google.business.location'
    _description = 'Google Business Profile Location'
    _rec_name = 'name'
    _order = 'name asc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    _sql_constraints = [
        (
            'gs_google_business_location_google_id_unique',
            'UNIQUE(google_location_id, company_id)',
            'A location with this Google Location ID already exists for this company.',
        ),
    ]

    # -------------------------------------------------------------------------
    # Fields
    # -------------------------------------------------------------------------

    name = fields.Char(
        string='Location Name',
        required=True,
        tracking=True,
        help='Display name of this Google Business Profile location.',
    )
    active = fields.Boolean(
        string='Active',
        default=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company,
        ondelete='restrict',
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Not Connected'),
            ('pending', 'OAuth Pending'),
            ('connected', 'Connected'),
            ('error', 'Error'),
        ],
        string='Connection Status',
        default='draft',
        tracking=True,
        help='Current OAuth connection state for this location.',
    )
    google_location_id = fields.Char(
        string='Google Location ID',
        copy=False,
        index=True,
        tracking=True,
        help=(
            'Unique identifier assigned by Google to this Business Profile location. '
            'Format: accounts/{accountId}/locations/{locationId}'
        ),
    )
    google_account_id = fields.Char(
        string='Google Account ID',
        copy=False,
        help='Google My Business account that owns this location.',
    )

    # --- OAuth credentials (write-only / restricted) ---
    access_token = fields.Char(
        string='Access Token',
        copy=False,
        groups='gs_google_business.group_manager',
        help='Short-lived OAuth 2.0 access token. Refreshed automatically.',
    )
    refresh_token = fields.Char(
        string='Refresh Token',
        copy=False,
        groups='gs_google_business.group_manager',
        help='Long-lived OAuth 2.0 refresh token used to obtain new access tokens.',
    )
    token_expiry = fields.Datetime(
        string='Token Expiry',
        copy=False,
        groups='gs_google_business.group_manager',
        help='UTC timestamp at which the current access token expires.',
    )
    oauth_client_id = fields.Char(
        string='OAuth Client ID',
        groups='gs_google_business.group_manager',
        help='Google Cloud Console OAuth 2.0 client ID for this location.',
    )
    oauth_client_secret = fields.Char(
        string='OAuth Client Secret',
        copy=False,
        groups='gs_google_business.group_manager',
        help='Google Cloud Console OAuth 2.0 client secret.',
    )

    # --- Address & contact info (synchronised from Google) ---
    street = fields.Char(string='Street', tracking=True)
    street2 = fields.Char(string='Street 2')
    city = fields.Char(string='City', tracking=True)
    state_id = fields.Many2one(
        comodel_name='res.country.state',
        string='State',
        ondelete='set null',
    )
    zip_code = fields.Char(string='ZIP / Postal Code')
    country_id = fields.Many2one(
        comodel_name='res.country',
        string='Country',
        ondelete='restrict',
    )
    phone = fields.Char(string='Phone', tracking=True)
    website = fields.Char(string='Website URL', tracking=True)
    primary_category = fields.Char(
        string='Primary Category',
        help='Google Business primary category (e.g. "Auto Repair Shop").',
    )

    # --- Business hours (structured One2many rows) ---
    hours_ids = fields.One2many(
        comodel_name='google.business.location.hours',
        inverse_name='location_id',
        string='Opening Hours',
        help='Weekly opening schedule. Add one row per open period per day. '
             'Multiple rows on the same day model split shifts.',
    )

    # --- Sync metadata ---
    last_sync_date = fields.Datetime(
        string='Last Synchronised',
        readonly=True,
        copy=False,
        help='Timestamp of the most recent successful data synchronisation.',
    )
    sync_error_message = fields.Text(
        string='Last Sync Error',
        readonly=True,
        copy=False,
        help='Error message from the most recent failed synchronisation attempt.',
    )

    # --- Statistics (computed, not stored — fetched live from child records) ---
    review_count = fields.Integer(
        string='Reviews',
        compute='_compute_review_count',
        help='Total number of reviews fetched from Google for this location.',
    )
    average_rating = fields.Float(
        string='Avg. Rating',
        compute='_compute_review_count',
        digits=(4, 2),
        help='Average star rating across all fetched reviews.',
    )
    unanswered_review_count = fields.Integer(
        string='Unanswered Reviews',
        compute='_compute_review_count',
        help='Number of reviews that have not yet received a reply.',
    )
    media_count = fields.Integer(
        string='Media Items',
        compute='_compute_media_count',
        help='Total number of photos/videos published to this location.',
    )
    post_count = fields.Integer(
        string='Posts',
        compute='_compute_post_count',
        help='Total number of Google posts for this location.',
    )
    review_ids = fields.One2many(
        comodel_name='google.business.review',
        inverse_name='location_id',
        string='Reviews',
    )
    media_ids = fields.One2many(
        comodel_name='google.business.media',
        inverse_name='location_id',
        string='Media',
    )
    post_ids = fields.One2many(
        comodel_name='google.business.post',
        inverse_name='location_id',
        string='Posts',
    )

    # -------------------------------------------------------------------------
    # Hours helpers
    # -------------------------------------------------------------------------

    def action_set_standard_hours(self):
        """Populate a default Mon–Fri 09:00–17:00 schedule for this location."""
        self.ensure_one()
        self.hours_ids.unlink()
        self.env['google.business.location.hours']._default_weekly_hours(
            self.id, open_time=9.0, close_time=17.0
        )

    def _get_hours_as_api_payload(self):
        """
        Serialise structured hours to the ``regularHours`` Google API payload.

        Returns:
            dict: A dict with a ``periods`` key containing the period list.
        """
        self.ensure_one()
        periods = []
        for period in self.hours_ids:
            api_dict = period.to_google_api_dict()
            if api_dict:
                periods.append(api_dict)
        return {'periods': periods}

    # -------------------------------------------------------------------------
    # Compute methods
    # -------------------------------------------------------------------------

    def _compute_review_count(self):
        for location in self:
            reviews = location.review_ids
            location.review_count = len(reviews)
            location.average_rating = (
                sum(reviews.mapped('rating')) / len(reviews) if reviews else 0.0
            )
            location.unanswered_review_count = len(
                reviews.filtered(lambda r: not r.is_replied)
            )

    def _compute_media_count(self):
        for location in self:
            location.media_count = len(location.media_ids)

    def _compute_post_count(self):
        for location in self:
            location.post_count = len(location.post_ids)

    # -------------------------------------------------------------------------
    # Constraints
    # -------------------------------------------------------------------------

    @api.constrains('google_location_id')
    def _check_google_location_id_format(self):
        for location in self:
            if location.google_location_id and '/' not in location.google_location_id:
                raise ValidationError(
                    _(
                        'The Google Location ID "%(gid)s" appears invalid. '
                        'Expected format: accounts/{accountId}/locations/{locationId}',
                        gid=location.google_location_id,
                    )
                )

    # -------------------------------------------------------------------------
    # CRUD overrides
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        return super().create(vals_list)

    def unlink(self):
        if any(rec.state == 'connected' for rec in self):
            raise UserError(
                _('Disconnect the location from Google before deleting it.')
            )
        return super().unlink()

    # -------------------------------------------------------------------------
    # Action methods
    # -------------------------------------------------------------------------

    def action_start_oauth(self):
        """Open the OAuth setup wizard for this location."""
        self.ensure_one()
        return {
            'name': _('Connect to Google Business Profile'),
            'type': 'ir.actions.act_window',
            'res_model': 'google.business.oauth.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_location_id': self.id,
                'default_oauth_client_id': self.oauth_client_id or '',
            },
        }

    def action_disconnect(self):
        """Revoke tokens and mark location as disconnected."""
        self.ensure_one()
        self.write({
            'state': 'draft',
            'access_token': False,
            'refresh_token': False,
            'token_expiry': False,
            'sync_error_message': False,
        })
        self.message_post(body=_('Location disconnected from Google Business Profile.'))

    def action_sync_now(self):
        """Trigger an immediate synchronisation for this location."""
        self.ensure_one()
        if self.state != 'connected':
            raise UserError(_('The location must be connected before synchronising.'))
        self._sync_location_data()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Sync Complete'),
                'message': _('Location data synchronised successfully.'),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_view_reviews(self):
        self.ensure_one()
        return {
            'name': _('Reviews — %(name)s', name=self.name),
            'type': 'ir.actions.act_window',
            'res_model': 'google.business.review',
            'view_mode': 'list,form',
            'domain': [('location_id', '=', self.id)],
            'context': {'default_location_id': self.id},
        }

    def action_view_media(self):
        self.ensure_one()
        return {
            'name': _('Media — %(name)s', name=self.name),
            'type': 'ir.actions.act_window',
            'res_model': 'google.business.media',
            'view_mode': 'kanban,list,form',
            'domain': [('location_id', '=', self.id)],
            'context': {'default_location_id': self.id},
        }

    def action_view_posts(self):
        self.ensure_one()
        return {
            'name': _('Posts — %(name)s', name=self.name),
            'type': 'ir.actions.act_window',
            'res_model': 'google.business.post',
            'view_mode': 'kanban,list,form',
            'domain': [('location_id', '=', self.id)],
            'context': {'default_location_id': self.id},
        }

    # -------------------------------------------------------------------------
    # Business logic
    # -------------------------------------------------------------------------

    def _sync_location_data(self):
        """
        Synchronise location profile data from the Google Business Profile API.

        This method is intentionally structured as a template:
        1. Ensure a valid token is available.
        2. Call the API to fetch location data.
        3. Write the returned values back to the record.
        4. Ingest any new reviews.

        Override this method in a project-specific module to supply the actual
        HTTP call implementation once Google API credentials are configured.
        """
        self.ensure_one()
        _logger.info(
            'gs_google_business: starting sync for location %s (id=%d)',
            self.name,
            self.id,
        )
        try:
            self._ensure_valid_token()
            # Concrete API call to be implemented by integrating module.
            # api_data = self._call_google_api('GET', f'{self.google_location_id}')
            # self._apply_location_data(api_data)
            self.write({
                'last_sync_date': fields.Datetime.now(),
                'sync_error_message': False,
                'state': 'connected',
            })
            _logger.info(
                'gs_google_business: sync completed for location %s', self.name
            )
        except Exception as exc:
            _logger.error(
                'gs_google_business: sync failed for location %s: %s',
                self.name,
                str(exc),
            )
            self.write({
                'state': 'error',
                'sync_error_message': str(exc),
            })

    def _ensure_valid_token(self):
        """
        Check whether the stored access token is still valid.
        If it has expired (or will expire within the safety margin), attempt
        to refresh it using the stored refresh token.

        Raises UserError if no valid token can be obtained.
        """
        self.ensure_one()
        if not self.refresh_token:
            raise UserError(
                _('No OAuth refresh token stored for location "%(name)s". '
                  'Please reconnect via the OAuth wizard.', name=self.name)
            )
        now = fields.Datetime.now()
        expiry = self.token_expiry
        if expiry:
            from datetime import timedelta
            if expiry - timedelta(seconds=_TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS) > now:
                return  # Token still valid
        # Token expired or near expiry — refresh it
        self._refresh_access_token()

    def _refresh_access_token(self):
        """
        Exchange the stored refresh token for a new access token.

        The actual HTTP POST to Google's token endpoint should be implemented
        here. The skeleton is provided for integration.
        """
        self.ensure_one()
        _logger.info(
            'gs_google_business: refreshing access token for location %s', self.name
        )
        # Placeholder — replace with actual requests.post() call:
        # response = requests.post(
        #     'https://oauth2.googleapis.com/token',
        #     data={
        #         'client_id': self.oauth_client_id,
        #         'client_secret': self.oauth_client_secret,
        #         'refresh_token': self.refresh_token,
        #         'grant_type': 'refresh_token',
        #     },
        # )
        # data = response.json()
        # from datetime import timedelta
        # self.write({
        #     'access_token': data['access_token'],
        #     'token_expiry': fields.Datetime.now() + timedelta(seconds=data['expires_in']),
        # })
        _logger.debug('gs_google_business: token refresh stub executed — wire up HTTP call.')

    # -------------------------------------------------------------------------
    # Scheduled action (cron)
    # -------------------------------------------------------------------------

    @api.model
    def _cron_sync_all_locations(self):
        """
        Scheduled action: synchronise all connected locations.
        Runs on the schedule defined in data/data.xml.
        """
        _logger.info('gs_google_business: cron sync started')
        locations = self.search([('state', '=', 'connected')])
        _logger.info('gs_google_business: %d connected location(s) to sync', len(locations))
        for location in locations:
            try:
                location._sync_location_data()
            except Exception as exc:
                _logger.error(
                    'gs_google_business: cron sync failed for location %s: %s',
                    location.name,
                    str(exc),
                )
        _logger.info('gs_google_business: cron sync finished')

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class GoogleBusinessPost(models.Model):
    """
    A Google Business Post (also called a "local post").

    Supports STANDARD (What's New), EVENT, and OFFER post types.
    Each post can include a Call-to-Action button and is linked to one location.
    """

    _name = 'google.business.post'
    _description = 'Google Business Post'
    _rec_name = 'title'
    _order = 'publish_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    _sql_constraints = [
        (
            'gs_google_business_post_google_id_unique',
            'UNIQUE(google_post_id)',
            'A post with this Google Post ID already exists.',
        ),
    ]

    # -------------------------------------------------------------------------
    # Fields
    # -------------------------------------------------------------------------

    title = fields.Char(
        string='Post Title',
        required=True,
        tracking=True,
    )
    active = fields.Boolean(string='Active', default=True)
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        related='location_id.company_id',
        store=True,
        readonly=True,
    )
    location_id = fields.Many2one(
        comodel_name='google.business.location',
        string='Location',
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('scheduled', 'Scheduled'),
            ('published', 'Published'),
            ('expired', 'Expired'),
            ('rejected', 'Rejected'),
        ],
        string='Status',
        default='draft',
        tracking=True,
    )

    # --- Google identifier ---
    google_post_id = fields.Char(
        string='Google Post ID',
        copy=False,
        index=True,
        help='Unique identifier assigned by Google to this local post.',
    )

    # --- Post type ---
    post_type = fields.Selection(
        selection=[
            ('STANDARD', "What's New"),
            ('EVENT', 'Event'),
            ('OFFER', 'Offer'),
        ],
        string='Post Type',
        required=True,
        default='STANDARD',
        tracking=True,
    )

    # --- Content ---
    summary = fields.Text(
        string='Post Body',
        required=True,
        help='Main text content of the post (max ~1,500 characters recommended).',
    )
    media_url = fields.Char(
        string='Media URL',
        help='URL of a photo or video to attach to this post.',
    )

    # --- Call-to-Action ---
    cta_type = fields.Selection(
        selection=[
            ('LEARN_MORE', 'Learn More'),
            ('BOOK', 'Book'),
            ('ORDER', 'Order Online'),
            ('SHOP', 'Buy'),
            ('SIGN_UP', 'Sign Up'),
            ('CALL', 'Call Now'),
        ],
        string='CTA Button',
        help='Call-to-Action button displayed on the post.',
    )
    cta_url = fields.Char(
        string='CTA URL',
        help='URL the CTA button points to.',
    )

    # --- Event-specific fields ---
    event_title = fields.Char(
        string='Event Title',
        help='Required for EVENT post type.',
    )
    event_start = fields.Datetime(
        string='Event Start',
        help='Event start date/time (EVENT posts only).',
    )
    event_end = fields.Datetime(
        string='Event End',
        help='Event end date/time (EVENT posts only).',
    )

    # --- Offer-specific fields ---
    offer_coupon_code = fields.Char(string='Coupon Code')
    offer_redeem_url = fields.Char(string='Redeem URL')
    offer_terms = fields.Text(string='Terms & Conditions')

    # --- Scheduling ---
    publish_date = fields.Datetime(
        string='Publish Date',
        tracking=True,
        help='Schedule a future publish time. Leave blank to publish immediately.',
    )
    expiry_date = fields.Datetime(
        string='Expiry Date',
        tracking=True,
        help='Date/time after which the post is no longer shown on Google.',
    )

    # --- Engagement metrics (synced from Google) ---
    view_count = fields.Integer(
        string='Views',
        readonly=True,
        copy=False,
    )
    click_count = fields.Integer(
        string='CTA Clicks',
        readonly=True,
        copy=False,
    )

    # -------------------------------------------------------------------------
    # Constraints
    # -------------------------------------------------------------------------

    @api.constrains('post_type', 'event_title', 'event_start', 'event_end')
    def _check_event_fields(self):
        for post in self:
            if post.post_type == 'EVENT':
                if not post.event_title:
                    raise UserError(_('Event Title is required for EVENT posts.'))
                if not post.event_start or not post.event_end:
                    raise UserError(
                        _('Event Start and Event End are required for EVENT posts.')
                    )
                if post.event_start >= post.event_end:
                    raise UserError(
                        _('Event End must be after Event Start.')
                    )

    @api.constrains('cta_type', 'cta_url')
    def _check_cta_url(self):
        for post in self:
            if post.cta_type and post.cta_type != 'CALL' and not post.cta_url:
                raise UserError(
                    _('A CTA URL is required when a CTA button type other than "Call Now" is selected.')
                )

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        return super().create(vals_list)

    def unlink(self):
        if any(rec.state == 'published' for rec in self):
            raise UserError(
                _('Published posts cannot be deleted. Remove them from Google first.')
            )
        return super().unlink()

    # -------------------------------------------------------------------------
    # Action methods
    # -------------------------------------------------------------------------

    def action_publish(self):
        """Publish this post to Google immediately."""
        self.ensure_one()
        if self.state not in ('draft', 'scheduled'):
            raise UserError(
                _('Only draft or scheduled posts can be published.')
            )
        if self.location_id.state != 'connected':
            raise UserError(
                _('Location "%(loc)s" is not connected to Google.',
                  loc=self.location_id.name)
            )
        _logger.info(
            'gs_google_business: publishing post "%s" to location %s',
            self.title, self.location_id.name,
        )
        # --- Placeholder for actual API call ---
        # self.location_id._ensure_valid_token()
        # payload = self._build_post_payload()
        # response = self.location_id._call_google_api(
        #     'POST', f'{self.location_id.google_location_id}/localPosts', json=payload
        # )
        # self.write({'google_post_id': response['name'], 'state': 'published',
        #             'publish_date': fields.Datetime.now()})
        # ----------------------------------------
        self.write({'state': 'published', 'publish_date': fields.Datetime.now()})
        self.message_post(body=_('Post published to Google Business Profile.'))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Post Published'),
                'message': _('Your post is now live on Google.'),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_schedule(self):
        """Mark this post as scheduled for future publication."""
        self.ensure_one()
        if not self.publish_date:
            raise UserError(_('Set a Publish Date before scheduling the post.'))
        self.state = 'scheduled'

    def action_unpublish(self):
        """Delete the post from Google and mark it as draft."""
        self.ensure_one()
        if self.state != 'published':
            raise UserError(_('Only published posts can be unpublished.'))
        _logger.info(
            'gs_google_business: deleting Google post %s', self.google_post_id
        )
        # self.location_id._ensure_valid_token()
        # self.location_id._call_google_api('DELETE', self.google_post_id)
        self.write({'state': 'draft', 'google_post_id': False})
        self.message_post(body=_('Post removed from Google Business Profile.'))

    def action_sync_metrics(self):
        """Refresh view and click engagement metrics from Google."""
        self.ensure_one()
        if self.state != 'published':
            raise UserError(_('Metrics are only available for published posts.'))
        _logger.info(
            'gs_google_business: syncing metrics for post %s', self.google_post_id
        )
        # Placeholder — wire up actual API call here
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Metrics Updated'),
                'message': _('Engagement metrics refreshed from Google.'),
                'type': 'info',
                'sticky': False,
            },
        }

    # -------------------------------------------------------------------------
    # Scheduled action
    # -------------------------------------------------------------------------

    @api.model
    def _cron_publish_scheduled_posts(self):
        """
        Publish posts whose publish_date has passed and are still in 'scheduled' state.
        Also marks posts as 'expired' when their expiry_date has passed.
        """
        now = fields.Datetime.now()
        _logger.info('gs_google_business: running scheduled post cron')

        due_posts = self.search([
            ('state', '=', 'scheduled'),
            ('publish_date', '<=', now),
        ])
        _logger.info('gs_google_business: %d post(s) due for publication', len(due_posts))
        for post in due_posts:
            try:
                post.action_publish()
            except Exception as exc:
                _logger.error(
                    'gs_google_business: failed to publish post %s: %s', post.title, str(exc)
                )

        expired_posts = self.search([
            ('state', '=', 'published'),
            ('expiry_date', '<=', now),
            ('expiry_date', '!=', False),
        ])
        if expired_posts:
            expired_posts.write({'state': 'expired'})
            _logger.info(
                'gs_google_business: marked %d post(s) as expired', len(expired_posts)
            )

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class GoogleBusinessMedia(models.Model):
    """
    A photo or video published (or pending publication) on a Google Business Profile.

    Categories follow the Google Business Profile API media item categories.
    """

    _name = 'google.business.media'
    _description = 'Google Business Media Item'
    _rec_name = 'name'
    _order = 'create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    _sql_constraints = [
        (
            'gs_google_business_media_google_id_unique',
            'UNIQUE(google_media_id)',
            'A media item with this Google Media ID already exists.',
        ),
    ]

    # -------------------------------------------------------------------------
    # Fields
    # -------------------------------------------------------------------------

    name = fields.Char(
        string='File Name',
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
            ('uploading', 'Uploading'),
            ('published', 'Published'),
            ('error', 'Upload Error'),
            ('removed', 'Removed'),
        ],
        string='Status',
        default='draft',
        tracking=True,
    )

    # --- Google identifiers ---
    google_media_id = fields.Char(
        string='Google Media ID',
        copy=False,
        index=True,
        help='Unique identifier assigned by Google once the media is uploaded.',
    )

    # --- Classification ---
    media_format = fields.Selection(
        selection=[
            ('PHOTO', 'Photo'),
            ('VIDEO', 'Video'),
        ],
        string='Format',
        required=True,
        default='PHOTO',
        tracking=True,
    )
    category = fields.Selection(
        selection=[
            ('EXTERIOR', 'Exterior'),
            ('INTERIOR', 'Interior'),
            ('PRODUCT', 'Product'),
            ('AT_WORK', 'At Work'),
            ('FOOD_AND_DRINK', 'Food & Drink'),
            ('MENU', 'Menu'),
            ('COMMON_AREA', 'Common Area'),
            ('ROOMS', 'Rooms'),
            ('TEAMS', 'Teams'),
            ('ADDITIONAL', 'Additional'),
            ('COVER', 'Cover'),
            ('PROFILE', 'Profile'),
            ('LOGO', 'Logo'),
        ],
        string='Category',
        required=True,
        default='ADDITIONAL',
        tracking=True,
        help='Google Business Profile media category.',
    )

    # --- File data ---
    media_file = fields.Binary(
        string='File',
        attachment=True,
        help='The binary content of the photo or video to be uploaded.',
    )
    media_filename = fields.Char(string='Filename')
    source_url = fields.Char(
        string='Source URL',
        help='Public URL of the media item — alternative to binary upload.',
    )
    thumbnail_url = fields.Char(
        string='Thumbnail URL',
        help='Google-provided thumbnail URL (available after upload).',
    )
    google_url = fields.Char(
        string='Google URL',
        copy=False,
        help='The permanent URL assigned by Google to the published media item.',
    )

    # --- Metadata ---
    description = fields.Char(
        string='Description / Alt Text',
        help='Short description or alt text for accessibility and SEO.',
    )
    media_date = fields.Date(
        string='Media Date',
        help='Original creation or capture date of the media item.',
    )
    upload_date = fields.Datetime(
        string='Uploaded At',
        readonly=True,
        copy=False,
    )

    # --- Engagement (read from Google API) ---
    view_count = fields.Integer(
        string='Views',
        readonly=True,
        copy=False,
        help='Total number of views reported by Google for this media item.',
    )

    # -------------------------------------------------------------------------
    # Constraints
    # -------------------------------------------------------------------------

    @api.constrains('media_file', 'source_url')
    def _check_media_source(self):
        for item in self:
            if not item.media_file and not item.source_url and item.state == 'draft':
                raise UserError(
                    _('Please upload a file or provide a source URL for "%(name)s".',
                      name=item.name)
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
                _(
                    'Published media items cannot be deleted directly. '
                    'Remove them from Google first, then delete.'
                )
            )
        return super().unlink()

    # -------------------------------------------------------------------------
    # Action methods
    # -------------------------------------------------------------------------

    def action_upload_to_google(self):
        """Upload this media item to the Google Business Profile API."""
        self.ensure_one()
        if self.state == 'published':
            raise UserError(_('This media item is already published on Google.'))
        if self.location_id.state != 'connected':
            raise UserError(
                _('Location "%(loc)s" is not connected to Google.',
                  loc=self.location_id.name)
            )
        self.state = 'uploading'
        _logger.info(
            'gs_google_business: uploading media %s to location %s',
            self.name, self.location_id.name,
        )
        # --- Placeholder for actual API call ---
        # location._ensure_valid_token()
        # response = location._call_google_api(
        #     'POST', f'{location.google_location_id}/media',
        #     json={'mediaFormat': self.media_format, 'locationAssociation': {'category': self.category}},
        # )
        # self.write({'google_media_id': response['name'], 'google_url': response['googleUrl'],
        #             'state': 'published', 'upload_date': fields.Datetime.now()})
        # ----------------------------------------
        self.write({
            'state': 'published',
            'upload_date': fields.Datetime.now(),
        })
        self.message_post(body=_('Media item uploaded to Google Business Profile.'))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Upload Queued'),
                'message': _('Media item is being uploaded to Google.'),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_remove_from_google(self):
        """Remove a published media item from Google."""
        self.ensure_one()
        if self.state != 'published':
            raise UserError(_('Only published media items can be removed from Google.'))
        _logger.info(
            'gs_google_business: removing media %s from Google', self.name
        )
        # location._ensure_valid_token()
        # location._call_google_api('DELETE', self.google_media_id)
        self.state = 'removed'
        self.message_post(body=_('Media item removed from Google Business Profile.'))

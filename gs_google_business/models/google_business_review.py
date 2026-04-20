import logging

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

STAR_RATING_MAP = {
    'ONE': 1,
    'TWO': 2,
    'THREE': 3,
    'FOUR': 4,
    'FIVE': 5,
}


class GoogleBusinessReview(models.Model):
    """
    A Google Business Profile review fetched via the GMB API.

    Reviews are read-only from Google's side; the only writable action
    Odoo performs is posting (or updating) a reply via the reply endpoint.
    """

    _name = 'google.business.review'
    _description = 'Google Business Review'
    _rec_name = 'reviewer_name'
    _order = 'review_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    _sql_constraints = [
        (
            'gs_google_business_review_google_id_unique',
            'UNIQUE(google_review_id)',
            'A review with this Google Review ID already exists.',
        ),
    ]

    # -------------------------------------------------------------------------
    # Fields
    # -------------------------------------------------------------------------

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
    google_review_id = fields.Char(
        string='Google Review ID',
        required=True,
        copy=False,
        index=True,
        help='Unique identifier assigned by Google to this review.',
    )

    # --- Reviewer ---
    reviewer_name = fields.Char(
        string='Reviewer',
        help='Display name of the reviewer as returned by the Google API.',
    )
    reviewer_profile_url = fields.Char(string='Reviewer Profile URL')
    reviewer_photo_url = fields.Char(string='Reviewer Photo URL')

    # --- Review content ---
    rating = fields.Integer(
        string='Star Rating',
        help='Numeric star rating (1–5).',
    )
    rating_label = fields.Selection(
        selection=[
            ('ONE', '★☆☆☆☆  (1)'),
            ('TWO', '★★☆☆☆  (2)'),
            ('THREE', '★★★☆☆  (3)'),
            ('FOUR', '★★★★☆  (4)'),
            ('FIVE', '★★★★★  (5)'),
        ],
        string='Rating',
        tracking=True,
        help='Star rating as returned by the Google API.',
    )
    review_text = fields.Text(
        string='Review Text',
        help='The full body of the reviewer\'s comment.',
    )
    review_date = fields.Datetime(
        string='Review Date',
        index=True,
        help='UTC timestamp at which the review was submitted.',
    )
    review_url = fields.Char(
        string='Review URL',
        help='Direct link to this review on Google Maps.',
    )

    # --- Reply tracking ---
    state = fields.Selection(
        selection=[
            ('new', 'New'),
            ('read', 'Read'),
            ('replied', 'Replied'),
            ('flagged', 'Flagged'),
        ],
        string='Status',
        default='new',
        tracking=True,
    )
    is_replied = fields.Boolean(
        string='Replied',
        compute='_compute_is_replied',
        store=True,
        help='True if at least one reply has been sent to Google.',
    )
    reply_ids = fields.One2many(
        comodel_name='google.business.review.reply',
        inverse_name='review_id',
        string='Reply History',
    )
    latest_reply_text = fields.Text(
        string='Current Reply',
        compute='_compute_latest_reply',
        store=True,
        help='The most recently published reply text visible on Google.',
    )
    latest_reply_date = fields.Datetime(
        string='Reply Date',
        compute='_compute_latest_reply',
        store=True,
    )
    assigned_user_id = fields.Many2one(
        comodel_name='res.users',
        string='Assigned To',
        ondelete='set null',
        tracking=True,
        help='Team member responsible for responding to this review.',
    )

    # -------------------------------------------------------------------------
    # Compute methods
    # -------------------------------------------------------------------------

    @api.depends('rating_label')
    def _compute_rating_from_label(self):
        for review in self:
            review.rating = STAR_RATING_MAP.get(review.rating_label, 0)

    @api.depends('reply_ids', 'reply_ids.is_published')
    def _compute_is_replied(self):
        for review in self:
            review.is_replied = any(
                reply.is_published for reply in review.reply_ids
            )

    @api.depends('reply_ids', 'reply_ids.is_published', 'reply_ids.reply_date')
    def _compute_latest_reply(self):
        for review in self:
            published = review.reply_ids.filtered('is_published').sorted(
                'reply_date', reverse=True
            )
            if published:
                review.latest_reply_text = published[0].reply_text
                review.latest_reply_date = published[0].reply_date
            else:
                review.latest_reply_text = False
                review.latest_reply_date = False

    # -------------------------------------------------------------------------
    # CRUD overrides
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('rating_label'):
                vals['rating'] = STAR_RATING_MAP.get(vals['rating_label'], 0)
        return super().create(vals_list)

    def unlink(self):
        if any(rec.state == 'replied' for rec in self):
            raise UserError(
                _('Replied reviews cannot be deleted. Archive them instead.')
            )
        return super().unlink()

    # -------------------------------------------------------------------------
    # Action methods
    # -------------------------------------------------------------------------

    def action_mark_read(self):
        for review in self.filtered(lambda r: r.state == 'new'):
            review.state = 'read'

    def action_flag(self):
        for review in self:
            review.state = 'flagged'

    def action_reply(self):
        """Open the reply wizard for a single review."""
        self.ensure_one()
        return {
            'name': _('Reply to Review'),
            'type': 'ir.actions.act_window',
            'res_model': 'google.business.reply.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_review_id': self.id,
                'default_location_id': self.location_id.id,
            },
        }

    def action_open_on_google(self):
        """Open this review directly on Google in a new browser tab."""
        self.ensure_one()
        if not self.review_url:
            raise UserError(_('No Google URL is stored for this review.'))
        return {
            'type': 'ir.actions.act_url',
            'url': self.review_url,
            'target': 'new',
        }

    # -------------------------------------------------------------------------
    # Business logic
    # -------------------------------------------------------------------------

    def _publish_reply_to_google(self, reply_text):
        """
        Post or update the reply to this review via the Google Business Profile API.

        Args:
            reply_text (str): The reply text to publish.

        Returns:
            google.business.review.reply: The newly created reply record.
        """
        self.ensure_one()
        if not reply_text or not reply_text.strip():
            raise UserError(_('Reply text cannot be empty.'))
        location = self.location_id
        if location.state != 'connected':
            raise UserError(
                _('Location "%(loc)s" is not connected to Google. '
                  'Complete the OAuth setup before replying.', loc=location.name)
            )
        _logger.info(
            'gs_google_business: publishing reply for review %s on location %s',
            self.google_review_id,
            location.name,
        )
        # --- Placeholder for actual API call ---
        # location._ensure_valid_token()
        # endpoint = f'{self.google_review_id}/reply'
        # location._call_google_api('PUT', endpoint, json={'comment': reply_text})
        # ----------------------------------------
        reply = self.env['google.business.review.reply'].create({
            'review_id': self.id,
            'reply_text': reply_text,
            'is_published': True,
            'reply_date': fields.Datetime.now(),
            'author_id': self.env.user.id,
        })
        self.state = 'replied'
        self.message_post(
            body=_('Reply published to Google: %s', reply_text),
            subtype_xmlid='mail.mt_note',
        )
        return reply


class GoogleBusinessReviewReply(models.Model):
    """
    Immutable audit log of every reply sent to a Google Business review.

    Each record represents one publish event. If a reply is updated,
    a new record is added so that the full reply history is preserved.
    """

    _name = 'google.business.review.reply'
    _description = 'Google Business Review Reply'
    _rec_name = 'reply_date'
    _order = 'reply_date desc'

    review_id = fields.Many2one(
        comodel_name='google.business.review',
        string='Review',
        required=True,
        ondelete='cascade',
        index=True,
    )
    reply_text = fields.Text(
        string='Reply Text',
        required=True,
    )
    reply_date = fields.Datetime(
        string='Published At',
        default=fields.Datetime.now,
        readonly=True,
    )
    author_id = fields.Many2one(
        comodel_name='res.users',
        string='Replied By',
        default=lambda self: self.env.user,
        ondelete='set null',
        readonly=True,
    )
    is_published = fields.Boolean(
        string='Published on Google',
        default=False,
    )
    canned_response_id = fields.Many2one(
        comodel_name='mail.canned.response',
        string='Canned Response Used',
        ondelete='set null',
        help='The canned response shortcut that was used to seed this reply (for analytics).',
    )

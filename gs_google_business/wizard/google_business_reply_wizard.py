import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class GoogleBusinessReplyWizard(models.TransientModel):
    """
    Wizard for composing and publishing a reply to a Google Business review.

    Integrates with Odoo's ``mail.canned.response`` engine so agents can
    use their existing shortcut library (type ':<shortcut>' to expand) to
    seed the reply, then personalise before publishing.
    """

    _name = 'google.business.reply.wizard'
    _description = 'Google Business Review Reply Wizard'

    review_id = fields.Many2one(
        comodel_name='google.business.review',
        string='Review',
        required=True,
        ondelete='cascade',
        readonly=True,
    )
    location_id = fields.Many2one(
        comodel_name='google.business.location',
        string='Location',
        related='review_id.location_id',
        readonly=True,
    )
    reviewer_name = fields.Char(
        string='Reviewer',
        related='review_id.reviewer_name',
        readonly=True,
    )
    rating_label = fields.Selection(
        related='review_id.rating_label',
        readonly=True,
    )
    review_text = fields.Text(
        string='Review',
        related='review_id.review_text',
        readonly=True,
    )
    existing_reply = fields.Text(
        string='Current Reply on Google',
        related='review_id.latest_reply_text',
        readonly=True,
    )

    # --- Composition ---
    canned_response_id = fields.Many2one(
        comodel_name='mail.canned.response',
        string='Canned Response',
        help=(
            'Select a canned response to pre-fill the reply body. '
            'You can also type ":" followed by a shortcut in the Reply field '
            'to trigger auto-complete.'
        ),
    )
    reply_text = fields.Text(
        string='Reply',
        required=True,
        help='Your reply to the reviewer. This will be published publicly on Google.',
    )
    is_update = fields.Boolean(
        string='Update Existing Reply',
        compute='_compute_is_update',
        help='True when updating a previously published reply.',
    )

    # -------------------------------------------------------------------------
    # Compute
    # -------------------------------------------------------------------------

    @api.depends('review_id', 'review_id.is_replied')
    def _compute_is_update(self):
        for wizard in self:
            wizard.is_update = wizard.review_id.is_replied

    # -------------------------------------------------------------------------
    # Onchange
    # -------------------------------------------------------------------------

    @api.onchange('canned_response_id')
    def _onchange_canned_response_id(self):
        if self.canned_response_id:
            self.reply_text = self.canned_response_id.substitution
            self.canned_response_id.last_used = fields.Datetime.now()

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def action_send_reply(self):
        """Validate and publish the reply to Google, then log the reply record."""
        self.ensure_one()
        if not self.reply_text or not self.reply_text.strip():
            raise UserError(_('Reply text cannot be empty.'))
        reply = self.review_id._publish_reply_to_google(self.reply_text)
        if self.canned_response_id:
            reply.canned_response_id = self.canned_response_id.id
        return {'type': 'ir.actions.act_window_close'}

    def action_save_draft(self):
        """Save the reply as a draft without publishing to Google."""
        self.ensure_one()
        if not self.reply_text or not self.reply_text.strip():
            raise UserError(_('Reply text cannot be empty.'))
        self.env['google.business.review.reply'].create({
            'review_id': self.review_id.id,
            'reply_text': self.reply_text,
            'is_published': False,
            'author_id': self.env.user.id,
            'canned_response_id': self.canned_response_id.id if self.canned_response_id else False,
        })
        self.review_id.message_post(
            body=_('Reply draft saved (not yet published to Google).'),
            subtype_xmlid='mail.mt_note',
        )
        return {'type': 'ir.actions.act_window_close'}

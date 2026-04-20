import logging
import math

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

_DAY_SEQUENCE = {
    'MONDAY': 1,
    'TUESDAY': 2,
    'WEDNESDAY': 3,
    'THURSDAY': 4,
    'FRIDAY': 5,
    'SATURDAY': 6,
    'SUNDAY': 7,
}


def _float_to_hhmm(value):
    """Convert a float hour value (e.g. 9.5) to an 'HH:MM' string."""
    if value is False or value is None:
        return ''
    hours = int(value)
    minutes = round((value - hours) * 60)
    return f'{hours:02d}:{minutes:02d}'


class GoogleBusinessLocationHours(models.Model):
    """
    Structured opening hours for a Google Business Profile location.

    Each row represents one time period for a given day. A day can have multiple
    rows to model split shifts (e.g. 09:00–13:00 and 15:00–21:00).
    Rows with ``is_closed=True`` indicate a full day closure.

    On sync, these rows are serialised to the Google API
    ``regularHours.periods`` format automatically.
    """

    _name = 'google.business.location.hours'
    _description = 'Google Business Opening Hours'
    _order = 'day_sequence, open_time'

    _sql_constraints = [
        (
            'gs_google_business_hours_unique_open',
            'UNIQUE(location_id, day_of_week, open_time)',
            'Duplicate opening time for the same day and location.',
        ),
    ]

    # -------------------------------------------------------------------------
    # Fields
    # -------------------------------------------------------------------------

    location_id = fields.Many2one(
        comodel_name='google.business.location',
        string='Location',
        required=True,
        ondelete='cascade',
        index=True,
    )
    day_of_week = fields.Selection(
        selection=[
            ('MONDAY', 'Monday'),
            ('TUESDAY', 'Tuesday'),
            ('WEDNESDAY', 'Wednesday'),
            ('THURSDAY', 'Thursday'),
            ('FRIDAY', 'Friday'),
            ('SATURDAY', 'Saturday'),
            ('SUNDAY', 'Sunday'),
        ],
        string='Day',
        required=True,
    )
    day_sequence = fields.Integer(
        string='Day Order',
        compute='_compute_day_sequence',
        store=True,
        help='Numeric sort order for day-of-week (Monday=1 … Sunday=7).',
    )
    is_closed = fields.Boolean(
        string='Closed',
        default=False,
        help='Mark this day as fully closed. Open/close times are ignored.',
    )
    open_time = fields.Float(
        string='Opens At',
        digits=(4, 2),
        help='Opening time as decimal hours (e.g. 9.5 = 09:30).',
    )
    close_time = fields.Float(
        string='Closes At',
        digits=(4, 2),
        help='Closing time as decimal hours (e.g. 17.0 = 17:00). '
             'Use 0.0 to indicate midnight (end of business day).',
    )
    open_time_display = fields.Char(
        string='Opens',
        compute='_compute_time_display',
        help='Human-readable opening time in HH:MM format.',
    )
    close_time_display = fields.Char(
        string='Closes',
        compute='_compute_time_display',
        help='Human-readable closing time in HH:MM format.',
    )
    note = fields.Char(
        string='Note',
        help='Optional note (e.g. "Kitchen closes at 22:00").',
    )

    # -------------------------------------------------------------------------
    # Compute
    # -------------------------------------------------------------------------

    @api.depends('day_of_week')
    def _compute_day_sequence(self):
        for rec in self:
            rec.day_sequence = _DAY_SEQUENCE.get(rec.day_of_week, 99)

    @api.depends('open_time', 'close_time', 'is_closed')
    def _compute_time_display(self):
        for rec in self:
            if rec.is_closed:
                rec.open_time_display = 'Closed'
                rec.close_time_display = '—'
            else:
                rec.open_time_display = _float_to_hhmm(rec.open_time)
                rec.close_time_display = _float_to_hhmm(rec.close_time)

    # -------------------------------------------------------------------------
    # Constraints
    # -------------------------------------------------------------------------

    @api.constrains('open_time', 'close_time', 'is_closed')
    def _check_time_order(self):
        for rec in self:
            if rec.is_closed:
                continue
            if rec.open_time < 0 or rec.open_time >= 24:
                raise ValidationError(
                    _('Open time must be between 00:00 and 23:59 for %(day)s.',
                      day=dict(self._fields['day_of_week'].selection).get(rec.day_of_week, ''))
                )
            if rec.close_time < 0 or rec.close_time > 24:
                raise ValidationError(
                    _('Close time must be between 00:00 and 24:00 for %(day)s.',
                      day=dict(self._fields['day_of_week'].selection).get(rec.day_of_week, ''))
                )
            if rec.close_time != 0.0 and rec.open_time >= rec.close_time:
                raise ValidationError(
                    _('Closing time must be after opening time for %(day)s.',
                      day=dict(self._fields['day_of_week'].selection).get(rec.day_of_week, ''))
                )

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        return super().create(vals_list)

    # -------------------------------------------------------------------------
    # Business logic
    # -------------------------------------------------------------------------

    def to_google_api_dict(self):
        """
        Serialise this hours record to the Google Business Profile API
        ``regularHours.periods`` element format.

        Returns:
            dict | None: A period dict or None if is_closed.
        """
        self.ensure_one()
        if self.is_closed:
            return None
        return {
            'openDay': self.day_of_week,
            'openTime': {'hours': int(self.open_time), 'minutes': round((self.open_time % 1) * 60)},
            'closeDay': self.day_of_week,
            'closeTime': {'hours': int(self.close_time), 'minutes': round((self.close_time % 1) * 60)},
        }

    @api.model
    def _default_weekly_hours(self, location_id, open_time=9.0, close_time=17.0):
        """
        Helper to create a standard Mon–Fri schedule and Sat–Sun closed rows
        for a given location. Called as a convenience during onboarding.
        """
        workdays = ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY']
        weekend = ['SATURDAY', 'SUNDAY']
        rows = []
        for day in workdays:
            rows.append({
                'location_id': location_id,
                'day_of_week': day,
                'open_time': open_time,
                'close_time': close_time,
            })
        for day in weekend:
            rows.append({
                'location_id': location_id,
                'day_of_week': day,
                'is_closed': True,
            })
        return self.create(rows)

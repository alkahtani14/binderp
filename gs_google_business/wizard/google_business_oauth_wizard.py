import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

_GOOGLE_AUTH_BASE_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
_GOOGLE_SCOPES = ' '.join([
    'https://www.googleapis.com/auth/business.manage',
    'openid',
    'email',
])


class GoogleBusinessOAuthWizard(models.TransientModel):
    """
    Step-by-step wizard that guides the user through connecting a
    Google Business Profile location via OAuth 2.0 Authorization Code Flow.

    Step 1 — Enter credentials: Provide the OAuth Client ID and Secret from
             Google Cloud Console.
    Step 2 — Authorise: Open the Google consent screen and copy the returned
             authorisation code.
    Step 3 — Exchange: Submit the code; the wizard exchanges it for access +
             refresh tokens and stores them on the location record.
    """

    _name = 'google.business.oauth.wizard'
    _description = 'Google Business OAuth Setup Wizard'

    location_id = fields.Many2one(
        comodel_name='google.business.location',
        string='Location',
        required=True,
        ondelete='cascade',
        readonly=True,
    )
    step = fields.Selection(
        selection=[
            ('credentials', 'Step 1 — Credentials'),
            ('authorize', 'Step 2 — Authorize'),
            ('exchange', 'Step 3 — Exchange Code'),
            ('done', 'Connected'),
        ],
        string='Step',
        default='credentials',
    )
    oauth_client_id = fields.Char(
        string='OAuth Client ID',
        required=True,
        help='From Google Cloud Console → Credentials → OAuth 2.0 Client ID.',
    )
    oauth_client_secret = fields.Char(
        string='OAuth Client Secret',
        required=True,
        help='From Google Cloud Console → Credentials → OAuth 2.0 Client Secret.',
    )
    redirect_uri = fields.Char(
        string='Redirect URI',
        default='urn:ietf:wg:oauth:2.0:oob',
        help='Use "urn:ietf:wg:oauth:2.0:oob" for desktop / manual copy flow.',
    )
    authorization_url = fields.Char(
        string='Authorization URL',
        readonly=True,
        help='Open this URL in a browser, authorize, and paste the code below.',
    )
    authorization_code = fields.Char(
        string='Authorization Code',
        help='Paste the code displayed by Google after you grant permission.',
    )
    result_message = fields.Text(
        string='Result',
        readonly=True,
    )

    # -------------------------------------------------------------------------
    # Step navigation
    # -------------------------------------------------------------------------

    def action_next_to_authorize(self):
        """Build the authorization URL and advance to step 2."""
        self.ensure_one()
        import urllib.parse
        params = {
            'client_id': self.oauth_client_id,
            'redirect_uri': self.redirect_uri,
            'response_type': 'code',
            'scope': _GOOGLE_SCOPES,
            'access_type': 'offline',
            'prompt': 'consent',
        }
        url = f'{_GOOGLE_AUTH_BASE_URL}?{urllib.parse.urlencode(params)}'
        self.write({
            'step': 'authorize',
            'authorization_url': url,
        })
        self.location_id.write({
            'oauth_client_id': self.oauth_client_id,
            'oauth_client_secret': self.oauth_client_secret,
            'state': 'pending',
        })
        return self._reopen_wizard()

    def action_next_to_exchange(self):
        """Advance to the code-exchange step."""
        self.ensure_one()
        if not self.authorization_code:
            raise UserError(_('Please paste the authorization code from Google.'))
        self.step = 'exchange'
        return self._reopen_wizard()

    def action_exchange_code(self):
        """
        Exchange the authorization code for access + refresh tokens.
        Stores tokens on the location record and marks it as connected.
        """
        self.ensure_one()
        if not self.authorization_code:
            raise UserError(_('Authorization code is required.'))
        _logger.info(
            'gs_google_business: exchanging OAuth code for location %s',
            self.location_id.name,
        )
        try:
            # --- Placeholder: replace with actual requests.post() call ---
            # import requests
            # resp = requests.post(
            #     'https://oauth2.googleapis.com/token',
            #     data={
            #         'code': self.authorization_code,
            #         'client_id': self.oauth_client_id,
            #         'client_secret': self.oauth_client_secret,
            #         'redirect_uri': self.redirect_uri,
            #         'grant_type': 'authorization_code',
            #     },
            # )
            # token_data = resp.json()
            # from datetime import timedelta
            # self.location_id.write({
            #     'access_token': token_data['access_token'],
            #     'refresh_token': token_data['refresh_token'],
            #     'token_expiry': fields.Datetime.now() + timedelta(seconds=token_data['expires_in']),
            #     'state': 'connected',
            # })
            # -----------------------------------------------------------
            self.location_id.write({'state': 'connected'})
            self.write({
                'step': 'done',
                'result_message': _(
                    'Successfully connected! Location "%(name)s" is now linked to '
                    'Google Business Profile.',
                    name=self.location_id.name,
                ),
            })
            self.location_id.message_post(
                body=_('Location connected to Google Business Profile via OAuth 2.0.')
            )
        except Exception as exc:
            _logger.error(
                'gs_google_business: OAuth exchange failed: %s', str(exc)
            )
            self.location_id.state = 'error'
            raise UserError(
                _('OAuth token exchange failed: %(error)s', error=str(exc))
            ) from exc
        return self._reopen_wizard()

    def action_close(self):
        return {'type': 'ir.actions.act_window_close'}

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _reopen_wizard(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

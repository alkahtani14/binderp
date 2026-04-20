import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class GoogleBusinessController(http.Controller):
    """
    HTTP routes for the Google Business Profile module.

    Currently provides an OAuth 2.0 callback endpoint for server-side
    redirect flows. When using the 'urn:ietf:wg:oauth:2.0:oob' (manual copy)
    flow this controller is not required; it is provided for future integration
    using a web-application redirect URI.
    """

    @http.route(
        '/google_business/oauth/callback',
        auth='user',
        type='http',
        methods=['GET'],
        csrf=False,
    )
    def oauth_callback(self, code=None, state=None, error=None, **kwargs):
        """
        Handle the OAuth 2.0 authorization code callback from Google.

        Google redirects here after the user grants (or denies) permission.
        The ``code`` parameter contains the authorization code to exchange
        for tokens, and ``state`` carries the location ID encoded by the wizard.

        Args:
            code (str): Authorization code from Google.
            state (str): Opaque state value (location_id encoded by the wizard).
            error (str): Error code if the user denied access.
        """
        if error:
            _logger.warning(
                'gs_google_business: OAuth callback received error: %s', error
            )
            return request.render(
                'gs_google_business.oauth_error_template',
                {'error': error},
            )

        if not code or not state:
            _logger.warning('gs_google_business: OAuth callback missing code or state')
            return request.redirect('/web')

        try:
            location_id = int(state)
        except (ValueError, TypeError):
            _logger.error(
                'gs_google_business: invalid state parameter in OAuth callback: %s', state
            )
            return request.redirect('/web')

        location = request.env['google.business.location'].browse(location_id)
        if not location.exists():
            _logger.error(
                'gs_google_business: location %d not found during OAuth callback', location_id
            )
            return request.redirect('/web')

        _logger.info(
            'gs_google_business: received OAuth callback for location %s', location.name
        )
        # Exchange the code for tokens:
        # location._exchange_code_for_tokens(code)
        # Redirect back to the location form:
        return request.redirect(f'/odoo/google-business/{location_id}')

"""gmail_auth.py: the one-time OAuth2 bootstrap for Gmail API access
(Appendix א §1.5) -- produces the token file `infra/email_sender.get_service()`
reads. Run once, by a human, before real Gmail sending can work; never
called automatically mid-match (a match should never silently try to pop
open a browser). Idempotent: safe to call again later -- refreshes an
expired token, or leaves an already-valid one untouched.
"""

from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from thief_peer.infra.email_sender import SCOPES


def _run_interactive_flow(credentials_path: str | Path) -> Credentials:
    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
    return flow.run_local_server(port=0)


def ensure_token(credentials_path: str | Path = "credentials.json", token_path: str | Path = "token.json") -> Path:
    token_path = Path(token_path)
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.valid:
        return token_path

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            # The refresh token itself is dead (revoked, or a Testing-mode
            # app's 7-day cap), not just the short-lived access token --
            # google.auth's own refresh() has no fallback for this, so
            # without this except the whole bootstrap crashes instead of
            # doing what its own docstring promises ("refreshes an expired
            # token, or leaves an already-valid one untouched" -- silently
            # failing a dead refresh token is neither).
            creds = _run_interactive_flow(credentials_path)
    else:
        creds = _run_interactive_flow(credentials_path)

    token_path.write_text(creds.to_json(), encoding="utf-8")
    return token_path

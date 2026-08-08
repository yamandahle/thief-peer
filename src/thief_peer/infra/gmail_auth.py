"""gmail_auth.py: the one-time OAuth2 bootstrap for Gmail API access
(Appendix א §1.5) -- produces the token file `infra/email_sender.get_service()`
reads. Run once, by a human, before real Gmail sending can work; never
called automatically mid-match (a match should never silently try to pop
open a browser). Idempotent: safe to call again later -- refreshes an
expired token, or leaves an already-valid one untouched.
"""

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from thief_peer.infra.email_sender import SCOPES


def ensure_token(credentials_path: str | Path = "credentials.json", token_path: str | Path = "token.json") -> Path:
    token_path = Path(token_path)
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.valid:
        return token_path

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
        creds = flow.run_local_server(port=0)

    token_path.write_text(creds.to_json(), encoding="utf-8")
    return token_path

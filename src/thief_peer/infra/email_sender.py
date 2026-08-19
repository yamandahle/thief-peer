"""Gmail reporting (PRD_7 §2.5, §3; Appendix א). A structured JSON report
is always sent as a MIME **attachment**, never inlined as a plain-text body
-- the book explicitly rejects plain-text bodies outright, zero score for
that game, even a JSON-*formatted* body still counts as "plain text" from
the API's perspective. Scope restricted to `gmail.send` only (least
privilege) -- this module never reads or modifies mail, only sends.
This module is never called directly by `report/report_writer.py`; only
through `shared/gatekeeper.py`'s `ApiGatekeeper.execute()` (PLAN.md ADR-4).
"""

import base64
import json
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def build_recipients(email_recipient: str, opponent_recipient: str | None, *, is_counted: bool) -> str:
    """The lecturer's own agent-reporting address (rule 51) always joins
    when the match is counted; a configured opponent address is always
    CC'd too, so both sides can cross-check the same artefacts without a
    separate manual send. `opponent_recipient` unset preserves the old,
    single-recipient behavior exactly. Comma-joined -- `MIMEMultipart`'s
    own "to" header already accepts multiple addresses that way, so no
    change is needed anywhere else in this module."""
    if opponent_recipient is None:
        return email_recipient
    recipients = [opponent_recipient]
    if is_counted:
        recipients.append(email_recipient)
    return ", ".join(recipients)


def get_service(token_path: str = "token.json"):
    """One-time browser consent already completed (Appendix א §1.5) leaves
    `token_path` reusable for unattended sending afterward."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    return build("gmail", "v1", credentials=creds)


def _canonical(payload: dict) -> str:
    """Rule 9.3.3's own required serialization for the attachment bytes --
    `sort_keys=True, ensure_ascii=False, separators=(",",":")`, distinct
    from `domain/crypto.py::canonical_json` (which is ASCII-only, fine for
    that module's always-ASCII payloads but not a safe substitute here,
    where a report can carry non-ASCII member names/hints). Confirmed
    live: yanell11's own cohort had a team's hashes match but its emailed
    report was a pretty-printed re-serialization instead of these exact
    bytes, and it nearly scored 0 -- `indent=2` was this module's own
    previous behavior for both the body and the attachment."""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def build_message(recipient: str, subject: str, report: dict) -> MIMEMultipart:
    message = MIMEMultipart()
    message["to"] = recipient
    message["subject"] = subject
    # Rule 9.3.3: the body must be the exact same canonical bytes as the
    # attachment -- never a prose note or a pretty-printed re-serialization
    # (this module's own attachment fix already exists for the identical
    # reason; a previous cohort nearly scored 0 on the body specifically).
    canonical_bytes = _canonical(report)
    message.attach(MIMEText(canonical_bytes, "plain"))

    attachment = MIMEApplication(canonical_bytes.encode("utf-8"), _subtype="json")
    # Rule 9.3.3: filename derives from game_id, not a fixed generic name.
    attachment.add_header("Content-Disposition", "attachment", filename=f"result_{report['game_id']}.json")
    message.attach(attachment)
    return message


def send_report(service, recipient: str, report: dict, subject: str | None = None) -> dict:
    message = build_message(recipient, subject or f"Police-Thief result {report['game_id']}", report)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return service.users().messages().send(userId="me", body={"raw": raw}).execute()

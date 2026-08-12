"""Gmail reporting (PRD_7 §2.5, §3; Appendix א). Structured JSON is always
a MIME **attachment**, never inlined as a plain-text body -- the book
rejects plain-text bodies (rule 34). Scope: `gmail.send` only.
Routed only through `ApiGatekeeper.execute()` (PLAN.md ADR-4).
"""

import base64
import json
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def get_service(token_path: str = "token.json"):
    """One-time browser consent already completed (Appendix א §1.5) leaves
    `token_path` reusable for unattended sending afterward."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    return build("gmail", "v1", credentials=creds)


def build_message(
    recipient: str,
    subject: str,
    attachments: dict[str, dict],
    body: str = "Structured match report attached as JSON (book Ch.9).",
) -> MIMEMultipart:
    """`attachments` maps filename -> JSON-serializable payload. Body is a
    short human pointer only — never the report itself (rule 34)."""
    message = MIMEMultipart()
    message["to"] = recipient
    message["subject"] = subject
    message.attach(MIMEText(body, "plain"))
    for filename, payload in attachments.items():
        part = MIMEApplication(json.dumps(payload, indent=2).encode("utf-8"), _subtype="json")
        part.add_header("Content-Disposition", "attachment", filename=filename)
        message.attach(part)
    return message


def send_report(
    service, recipient: str, report: dict, subject: str = "Police-Thief match report"
) -> dict:
    """Single-file report (legacy). Prefer `send_report_bundle` for Ch.9.3.3."""
    return send_report_bundle(service, recipient, {"report.json": report}, subject=subject)


def send_report_bundle(
    service,
    recipient: str,
    attachments: dict[str, dict],
    subject: str = "Police-Thief match report",
) -> dict:
    """All Table-20 JSON files on one message (declaration/config/log/result)."""
    message = build_message(recipient, subject, attachments)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return service.users().messages().send(userId="me", body={"raw": raw}).execute()

"""infra/email_sender.py tests (PRD_7 §2.5, §3, §5; Appendix א). A plain-text
report body is explicitly rejected by the book -- zero score for that game
-- so the report must always be a structured JSON *attachment*, never
inlined as text. These tests inspect the constructed MIME message object
directly, not just that "an email was sent" (PRD_7 §5's own framing)."""

import base64
import json

from thief_peer.infra.email_sender import SCOPES, build_message, send_report


def _sample_report():
    return {"game_id": "a-vs-b", "result": "survival", "step_count": 12}


def _attachments(report=None):
    return {"report.json": report or _sample_report()}


def test_scope_is_least_privilege_send_only():
    assert SCOPES == ["https://www.googleapis.com/auth/gmail.send"]


def test_build_message_has_a_json_attachment_part():
    message = build_message("grader@example.com", "Match report", _attachments())

    attachments = [
        part
        for part in message.walk()
        if part.get_content_disposition() == "attachment"
    ]
    assert len(attachments) == 1
    assert attachments[0].get_content_type() == "application/json"


def test_build_message_attachment_content_matches_the_report_exactly():
    report = _sample_report()
    message = build_message("grader@example.com", "Match report", _attachments(report))

    attachment = next(part for part in message.walk() if part.get_content_disposition() == "attachment")
    decoded = json.loads(attachment.get_payload(decode=True).decode("utf-8"))
    assert decoded == report


def test_build_message_body_text_does_not_contain_the_raw_report_json():
    report = _sample_report()
    message = build_message("grader@example.com", "Match report", _attachments(report))

    body_parts = [
        part
        for part in message.walk()
        if part.get_content_type() == "text/plain" and part.get_content_disposition() != "attachment"
    ]
    assert len(body_parts) == 1
    body_text = body_parts[0].get_payload(decode=True).decode("utf-8")
    assert json.dumps(report) not in body_text
    assert '"game_id"' not in body_text


def test_build_message_sets_recipient_and_subject():
    message = build_message("grader@example.com", "Match report: g01", _attachments())
    assert message["to"] == "grader@example.com"
    assert message["subject"] == "Match report: g01"


class _FakeMessages:
    def __init__(self):
        self.sent_body = None

    def send(self, userId, body):  # noqa: N803 -- must match the real Gmail API's kwarg name
        self.sent_body = body
        return self

    def execute(self):
        return {"id": "fake-message-id"}


class _FakeUsers:
    def __init__(self):
        self.messages_obj = _FakeMessages()

    def messages(self):
        return self.messages_obj


class _FakeService:
    def __init__(self):
        self.users_obj = _FakeUsers()

    def users(self):
        return self.users_obj


def test_send_report_submits_a_base64_encoded_raw_message():
    service = _FakeService()
    result = send_report(service, "grader@example.com", _sample_report())

    assert result == {"id": "fake-message-id"}
    raw = service.users_obj.messages_obj.sent_body["raw"]
    decoded_bytes = base64.urlsafe_b64decode(raw)
    assert b"attachment" in decoded_bytes.lower() or b"Content-Disposition" in decoded_bytes


def test_send_report_never_puts_the_report_directly_in_the_send_call_body():
    service = _FakeService()
    send_report(service, "grader@example.com", _sample_report())

    sent_body = service.users_obj.messages_obj.sent_body
    assert set(sent_body) == {"raw"}

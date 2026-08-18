"""infra/gmail_auth.py tests (Appendix א §1.5 follow-up). ensure_token() is
the one-time OAuth2 bootstrap that produces the token file
infra/email_sender.get_service() reads -- exercised entirely against
monkeypatched Credentials/Request/InstalledAppFlow, never a real browser or
Google's servers."""

from google.auth.exceptions import RefreshError

from thief_peer.infra import gmail_auth


class _FakeCreds:
    def __init__(self, valid=True, expired=False, refresh_token=None, json_blob="creds-json", raise_on_refresh=False):
        self.valid = valid
        self.expired = expired
        self.refresh_token = refresh_token
        self._json_blob = json_blob
        self._raise_on_refresh = raise_on_refresh
        self.refreshed = False

    def refresh(self, request):
        if self._raise_on_refresh:
            raise RefreshError("invalid_grant: Token has been expired or revoked.")
        self.refreshed = True

    def to_json(self):
        return self._json_blob


class _FakeCredentialsClass:
    def __init__(self, creds_to_return):
        self._creds_to_return = creds_to_return
        self.called_with = None

    def from_authorized_user_file(self, path, scopes):
        self.called_with = (path, scopes)
        return self._creds_to_return


class _FakeFlowInstance:
    def __init__(self, creds_to_return):
        self._creds_to_return = creds_to_return
        self.ran_local_server = False

    def run_local_server(self, port):
        self.ran_local_server = True
        return self._creds_to_return


class _FakeFlowClass:
    def __init__(self, instance):
        self._instance = instance
        self.called_with = None

    def from_client_secrets_file(self, path, scopes):
        self.called_with = (path, scopes)
        return self._instance


def test_ensure_token_runs_the_browser_flow_when_no_token_file_exists(tmp_path, monkeypatch):
    token_path = tmp_path / "token.json"
    new_creds = _FakeCreds(json_blob="new-token-json")
    flow_instance = _FakeFlowInstance(new_creds)
    flow_class = _FakeFlowClass(flow_instance)
    monkeypatch.setattr(gmail_auth, "InstalledAppFlow", flow_class)

    result_path = gmail_auth.ensure_token("credentials.json", token_path)

    assert result_path == token_path
    assert flow_instance.ran_local_server is True
    assert flow_class.called_with == ("credentials.json", gmail_auth.SCOPES)
    assert token_path.read_text(encoding="utf-8") == "new-token-json"


def test_ensure_token_leaves_an_already_valid_token_untouched(tmp_path, monkeypatch):
    token_path = tmp_path / "token.json"
    token_path.write_text("existing-valid-token", encoding="utf-8")

    valid_creds = _FakeCreds(valid=True)
    monkeypatch.setattr(gmail_auth, "Credentials", _FakeCredentialsClass(valid_creds))

    def _explode(*_a, **_k):
        raise AssertionError("must not run the browser flow when the token is already valid")

    monkeypatch.setattr(gmail_auth, "InstalledAppFlow", type("X", (), {"from_client_secrets_file": _explode}))

    result_path = gmail_auth.ensure_token("credentials.json", token_path)

    assert result_path == token_path
    assert token_path.read_text(encoding="utf-8") == "existing-valid-token"


def test_ensure_token_refreshes_an_expired_token_that_has_a_refresh_token(tmp_path, monkeypatch):
    token_path = tmp_path / "token.json"
    token_path.write_text("expired-token", encoding="utf-8")

    expired_creds = _FakeCreds(valid=False, expired=True, refresh_token="rt", json_blob="refreshed-json")
    monkeypatch.setattr(gmail_auth, "Credentials", _FakeCredentialsClass(expired_creds))
    monkeypatch.setattr(gmail_auth, "Request", lambda: None)

    def _explode(*_a, **_k):
        raise AssertionError("must not run the browser flow when a refresh token is available")

    monkeypatch.setattr(gmail_auth, "InstalledAppFlow", type("X", (), {"from_client_secrets_file": _explode}))

    gmail_auth.ensure_token("credentials.json", token_path)

    assert expired_creds.refreshed is True
    assert token_path.read_text(encoding="utf-8") == "refreshed-json"


def test_ensure_token_falls_back_to_the_browser_flow_when_the_refresh_token_is_dead(tmp_path, monkeypatch):
    # A revoked/expired refresh token (e.g. a Testing-mode OAuth app's
    # 7-day cap) raises RefreshError from creds.refresh() itself -- this
    # must fall back to the interactive flow, not crash (the real bug
    # this test guards: ensure_token used to let RefreshError propagate).
    token_path = tmp_path / "token.json"
    token_path.write_text("expired-dead-refresh-token", encoding="utf-8")

    expired_creds = _FakeCreds(valid=False, expired=True, refresh_token="rt", raise_on_refresh=True)
    monkeypatch.setattr(gmail_auth, "Credentials", _FakeCredentialsClass(expired_creds))
    monkeypatch.setattr(gmail_auth, "Request", lambda: None)

    new_creds = _FakeCreds(json_blob="new-token-after-dead-refresh")
    flow_instance = _FakeFlowInstance(new_creds)
    monkeypatch.setattr(gmail_auth, "InstalledAppFlow", _FakeFlowClass(flow_instance))

    gmail_auth.ensure_token("credentials.json", token_path)

    assert flow_instance.ran_local_server is True
    assert token_path.read_text(encoding="utf-8") == "new-token-after-dead-refresh"


def test_ensure_token_falls_back_to_the_browser_flow_without_a_refresh_token(tmp_path, monkeypatch):
    token_path = tmp_path / "token.json"
    token_path.write_text("expired-no-refresh", encoding="utf-8")

    expired_creds = _FakeCreds(valid=False, expired=True, refresh_token=None)
    monkeypatch.setattr(gmail_auth, "Credentials", _FakeCredentialsClass(expired_creds))

    new_creds = _FakeCreds(json_blob="new-token-after-fallback")
    flow_instance = _FakeFlowInstance(new_creds)
    monkeypatch.setattr(gmail_auth, "InstalledAppFlow", _FakeFlowClass(flow_instance))

    gmail_auth.ensure_token("credentials.json", token_path)

    assert flow_instance.ran_local_server is True
    assert token_path.read_text(encoding="utf-8") == "new-token-after-fallback"

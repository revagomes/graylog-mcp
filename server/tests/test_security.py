"""Security regression tests (Lagune-style review).

Findings addressed:
- Cleartext token transmission: GRAYLOG_URL was not required to be HTTPS, so a
  misconfigured http:// URL would send the REST API token (HTTP Basic) in
  cleartext. Now rejected before any request is made. (CWE-319)
- Silent TLS-verification disable: GRAYLOG_VERIFY_TLS=false disables cert
  verification (a documented internal-CA escape hatch) but did so silently,
  hiding MITM exposure. Now emits a one-time stderr warning. (CWE-295)

Invariants guarded: the token never leaves over cleartext HTTP, and disabling
TLS verification is a visible, conscious choice.
"""

import importlib
import sys

import pytest


class FakeResponse:
    def __init__(self, status_code=200, json_body=None):
        self.status_code = status_code
        self._json = json_body if json_body is not None else {}
        self.text = ""
        self.headers = {}
        self.content = b"{}"
        self.ok = 200 <= status_code < 300

    @property
    def is_redirect(self):
        return False

    def json(self):
        return self._json


def _reload_with(monkeypatch, **env):
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)
    if "graylog_mcp" in sys.modules:
        return importlib.reload(sys.modules["graylog_mcp"])
    return importlib.import_module("graylog_mcp")


def test_http_url_is_rejected_before_any_request(monkeypatch):
    """A cleartext http:// GRAYLOG_URL must be refused, and no request made."""
    g = _reload_with(
        monkeypatch,
        GRAYLOG_URL="http://graylog.example.com",
        GRAYLOG_TOKEN="secret-token",
        GRAYLOG_COOKIE=None,
        GRAYLOG_VERIFY_TLS="true",
    )
    called = {"hit": False}

    def fake_request(*a, **k):
        called["hit"] = True
        return FakeResponse()

    monkeypatch.setattr(g.requests, "request", fake_request)
    with pytest.raises(RuntimeError) as exc:
        g.graylog_system_status()
    assert "HTTPS" in str(exc.value) or "https" in str(exc.value)
    assert called["hit"] is False, "no request must be made over cleartext"


def test_https_url_is_allowed(monkeypatch):
    g = _reload_with(
        monkeypatch,
        GRAYLOG_URL="https://graylog.example.com",
        GRAYLOG_TOKEN="secret-token",
        GRAYLOG_COOKIE=None,
        GRAYLOG_VERIFY_TLS="true",
    )
    monkeypatch.setattr(g.requests, "request",
                        lambda *a, **k: FakeResponse(json_body={"version": "5"}))
    out = g.graylog_system_status()
    assert out["version"] == "5"


def test_disabling_tls_verification_warns(monkeypatch, capsys):
    g = _reload_with(
        monkeypatch,
        GRAYLOG_URL="https://graylog.example.com",
        GRAYLOG_TOKEN="secret-token",
        GRAYLOG_COOKIE=None,
        GRAYLOG_VERIFY_TLS="false",
    )
    monkeypatch.setattr(g.requests, "request",
                        lambda *a, **k: FakeResponse(json_body={"version": "5"}))
    g.graylog_system_status()
    err = capsys.readouterr().err.lower()
    assert "tls" in err and ("disabl" in err or "verif" in err)

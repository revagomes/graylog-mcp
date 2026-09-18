"""Behavioral tests for the Graylog MCP tools and helpers.

All HTTP is mocked at requests.request — no real Graylog call happens.
"""

import pytest


class FakeResponse:
    def __init__(self, status_code=200, json_body=None, text="", headers=None,
                 content=b"x"):
        self.status_code = status_code
        self._json = json_body
        self.text = text
        self.headers = headers or {}
        self.content = content if json_body is None else b"{}"
        self.ok = 200 <= status_code < 300

    @property
    def is_redirect(self):
        return self.status_code in (301, 302, 303, 307, 308)

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


def _install(gray, monkeypatch, response):
    """Patch requests.request to record the call and return `response`."""
    calls = []

    def fake_request(method, url, params=None, json=None, headers=None,
                     auth=None, verify=None, timeout=None, allow_redirects=None):
        calls.append({
            "method": method, "url": url, "params": params, "json": json,
            "headers": headers, "auth": auth, "verify": verify,
        })
        return response

    monkeypatch.setattr(gray.requests, "request", fake_request)
    return calls


# ── helpers ──────────────────────────────────────────────────────────────────

def test_auth_uses_token_as_username(gray):
    assert gray._auth() == ("test-token", "token")


def test_build_timerange_precedence(gray):
    # absolute > keyword > relative > default
    assert gray._build_timerange(60, "last hour", "2026-01-01", "2026-01-02") == {
        "type": "absolute", "from": "2026-01-01", "to": "2026-01-02"
    }
    assert gray._build_timerange(60, "last hour", None, None) == {
        "type": "keyword", "keyword": "last hour"
    }
    assert gray._build_timerange(60, None, None, None) == {
        "type": "relative", "range": 60
    }
    assert gray._build_timerange(None, None, None, None) == {
        "type": "relative", "range": 900
    }


def test_rows_to_dicts_maps_schema(gray):
    payload = {
        "schema": [{"field": "source"}, {"field": "count()"}],
        "datarows": [["web01", 5], ["web02", 3]],
    }
    rows = gray._rows_to_dicts(payload)
    assert rows == [{"source": "web01", "count()": 5},
                    {"source": "web02", "count()": 3}]


# ── search / aggregate ───────────────────────────────────────────────────────

def test_search_messages_builds_body_and_maps_rows(gray, monkeypatch):
    resp = FakeResponse(json_body={
        "schema": [{"field": "timestamp"}, {"field": "message"}],
        "datarows": [["t1", "boom"]],
        "metadata": {"effective_timerange": {"type": "relative", "range": 900}},
    })
    calls = _install(gray, monkeypatch, resp)
    out = gray.graylog_search_messages(query="error", size=10)
    assert out["count"] == 1
    assert out["messages"][0]["message"] == "boom"
    body = calls[-1]["json"]
    assert body["query"] == "error"
    assert body["size"] == 10


def test_aggregate_parses_metric_specs(gray, monkeypatch):
    resp = FakeResponse(json_body={"schema": [{"field": "source"}],
                                   "datarows": [["web01"]], "metadata": {}})
    calls = _install(gray, monkeypatch, resp)
    gray.graylog_aggregate(group_by=["source"], metrics=["avg:took_ms", "count"])
    body = calls[-1]["json"]
    assert {"function": "avg", "field": "took_ms"} in body["metrics"]
    assert {"function": "count"} in body["metrics"]
    assert body["group_by"] == [{"field": "source"}]


# ── inspection tools ─────────────────────────────────────────────────────────

def test_list_streams_filters_disabled(gray, monkeypatch):
    resp = FakeResponse(json_body={"streams": [
        {"id": "1", "title": "A", "disabled": False},
        {"id": "2", "title": "B", "disabled": True},
    ]})
    _install(gray, monkeypatch, resp)
    rows = gray.graylog_list_streams()
    assert [r["id"] for r in rows] == ["1"]


def test_system_status_extracts_fields(gray, monkeypatch):
    resp = FakeResponse(json_body={"version": "5.2", "hostname": "gl01",
                                   "cluster_id": "abc"})
    _install(gray, monkeypatch, resp)
    out = gray.graylog_system_status()
    assert out["version"] == "5.2"
    assert out["hostname"] == "gl01"


# ── error handling ───────────────────────────────────────────────────────────

def test_request_raises_on_401(gray, monkeypatch):
    _install(gray, monkeypatch, FakeResponse(status_code=401, content=b"nope"))
    with pytest.raises(RuntimeError) as exc:
        gray.graylog_system_status()
    assert "401" in str(exc.value)


def test_request_detects_sso_redirect(gray, monkeypatch):
    resp = FakeResponse(status_code=302,
                        headers={"location": "https://sso.example.com/sign_in?x=1"})
    _install(gray, monkeypatch, resp)
    with pytest.raises(RuntimeError) as exc:
        gray.graylog_system_status()
    assert "SSO" in str(exc.value) or "sign-in" in str(exc.value)


def test_request_raises_on_403(gray, monkeypatch):
    _install(gray, monkeypatch, FakeResponse(status_code=403, content=b"denied"))
    with pytest.raises(RuntimeError) as exc:
        gray.graylog_system_status()
    assert "403" in str(exc.value)


# ── remaining inspection tools ───────────────────────────────────────────────

def test_get_stream_extracts_rules(gray, monkeypatch):
    resp = FakeResponse(json_body={"id": "1", "title": "A",
                                   "rules": [{"field": "source"}]})
    _install(gray, monkeypatch, resp)
    out = gray.graylog_get_stream("1")
    assert out["id"] == "1"
    assert out["rules"] == [{"field": "source"}]


def test_list_index_sets(gray, monkeypatch):
    resp = FakeResponse(json_body={"index_sets": [
        {"id": "i1", "title": "Default", "index_prefix": "graylog"},
    ]})
    _install(gray, monkeypatch, resp)
    rows = gray.graylog_list_index_sets()
    assert rows[0]["index_prefix"] == "graylog"


def test_list_inputs_handles_message_input_wrapper(gray, monkeypatch):
    resp = FakeResponse(json_body={"inputs": [
        {"message_input": {"id": "in1", "title": "syslog", "type": "SyslogUDP"}},
    ]})
    _install(gray, monkeypatch, resp)
    rows = gray.graylog_list_inputs()
    assert rows[0]["id"] == "in1"
    assert rows[0]["type"] == "SyslogUDP"


def test_list_fields_sorted(gray, monkeypatch):
    resp = FakeResponse(json_body={"fields": ["source", "message", "level"]})
    _install(gray, monkeypatch, resp)
    rows = gray.graylog_list_fields()
    assert [r["name"] for r in rows] == ["level", "message", "source"]

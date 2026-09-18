"""Pytest fixtures for the Graylog MCP server.

The module reads its configuration from the environment into module-level
constants at import time, so the fixture sets test config and reloads the
module. All HTTP is mocked at the ``requests.request`` boundary — no real
Graylog instance or network call happens.
"""

import importlib
import os
import sys
import pathlib

import pytest

_SERVER_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVER_DIR))


@pytest.fixture()
def gray(monkeypatch):
    """Import a fresh copy of the server module with test config."""
    monkeypatch.setenv("GRAYLOG_URL", "https://graylog.example.com")
    monkeypatch.setenv("GRAYLOG_TOKEN", "test-token")
    monkeypatch.delenv("GRAYLOG_COOKIE", raising=False)
    monkeypatch.setenv("GRAYLOG_VERIFY_TLS", "true")
    monkeypatch.setenv("GRAYLOG_TIMEOUT", "30")

    if "graylog_mcp" in sys.modules:
        return importlib.reload(sys.modules["graylog_mcp"])
    return importlib.import_module("graylog_mcp")

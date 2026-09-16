#!/usr/bin/env python3
"""
Graylog MCP Server.

Copyright (C) 2026 Renato Vasconcellos Gomes

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

A local MCP server that connects to a self-hosted Graylog instance
(default: https://graylog.example.com) through its REST API.

It exposes clean tool interfaces over the stable Graylog "search scripting"
API (/api/search/messages and /api/search/aggregate) plus read-only
system, stream, index, and input inspection endpoints. This lets an LLM
search logs, summarize trends, and orient itself in the environment without
having to hand-craft Lucene queries, time ranges, and URL-encoded requests.

Authentication uses a Graylog REST API access token. Per Graylog convention,
the token is sent as the HTTP Basic *username* and the literal string
"token" as the *password*. No real username/password ever leaves the machine.

Configuration via environment variables:
    GRAYLOG_URL        - Base URL of the Graylog instance
                         (default: https://graylog.example.com)
    GRAYLOG_TOKEN      - REST API access token (required)
    GRAYLOG_VERIFY_TLS - "true"/"false" to toggle TLS verification (default: true)
    GRAYLOG_TIMEOUT    - Per-request timeout in seconds (default: 30)

Run via:
    uvx --from fastmcp --with requests fastmcp run server/graylog_mcp.py
"""

import os

import requests
from fastmcp import FastMCP

# -- Configuration --------------------------------------------------------------

GRAYLOG_URL = os.environ.get(
    "GRAYLOG_URL", "https://graylog.example.com"
).rstrip("/")
GRAYLOG_TOKEN = os.environ.get("GRAYLOG_TOKEN", "")
VERIFY_TLS = os.environ.get("GRAYLOG_VERIFY_TLS", "true").lower() != "false"
TIMEOUT = int(os.environ.get("GRAYLOG_TIMEOUT", "30"))

# Graylog REST API is served under /api on modern versions.
API_BASE = f"{GRAYLOG_URL}/api"

mcp = FastMCP(
    "Graylog",
    instructions=(
        "Graylog MCP server for a self-hosted Graylog instance. "
        "Use graylog_search_messages to run Lucene queries over a time range, "
        "graylog_aggregate to summarize trends (counts, averages, top values), "
        "and the list_* tools to discover streams, index sets, indices, and "
        "inputs before scoping a search. All operations are read-only. "
        "Always scope searches with a time range and, when possible, a stream "
        "to keep queries fast and relevant."
    ),
)


# -- Helpers --------------------------------------------------------------------


def _auth() -> tuple[str, str]:
    """Return the HTTP Basic auth pair for token authentication.

    Graylog convention: the access token is the username and the literal
    string "token" is the password.
    """
    if not GRAYLOG_TOKEN:
        raise RuntimeError(
            "GRAYLOG_TOKEN is not set. Create a REST API access token in "
            "Graylog (user menu -> Edit tokens) and set it in the MCP env."
        )
    return (GRAYLOG_TOKEN, "token")


def _headers(accept: str = "application/json") -> dict:
    """Standard headers. X-Requested-By is required by Graylog for API calls."""
    return {
        "Accept": accept,
        "Content-Type": "application/json",
        "X-Requested-By": "kiro-graylog-mcp",
    }


def _request(
    method: str,
    path: str,
    params: dict | None = None,
    json_body: dict | None = None,
    accept: str = "application/json",
) -> dict | list:
    """Perform a Graylog REST API request and return parsed JSON.

    Args:
        method: HTTP method (GET, POST, ...).
        path: API path relative to /api (e.g. "search/messages").
        params: Query string parameters.
        json_body: JSON request body for POST/PUT.
        accept: Accept header value.
    """
    url = f"{API_BASE}/{path.lstrip('/')}"
    try:
        response = requests.request(
            method,
            url,
            params=params,
            json=json_body,
            headers=_headers(accept),
            auth=_auth(),
            verify=VERIFY_TLS,
            timeout=TIMEOUT,
        )
    except requests.exceptions.SSLError as exc:
        raise RuntimeError(
            f"TLS verification failed for {url}. If this instance uses an "
            f"internal CA, set GRAYLOG_VERIFY_TLS=false. Details: {exc}"
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Request to {url} failed: {exc}") from exc

    if response.status_code == 401:
        raise RuntimeError(
            "Authentication failed (401). Check GRAYLOG_TOKEN is a valid, "
            "non-expired REST API access token."
        )
    if response.status_code == 403:
        raise RuntimeError(
            "Permission denied (403). The token's user lacks permission for "
            f"{path}. Grant the required role or narrow the request."
        )
    if not response.ok:
        detail = response.text.strip()
        raise RuntimeError(
            f"Graylog API error {response.status_code} on {path}: {detail[:500]}"
        )

    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text}


def _build_timerange(
    relative_seconds: int | None,
    keyword: str | None,
    time_from: str | None,
    time_to: str | None,
) -> dict:
    """Build a Graylog timerange object from the simplest provided input.

    Precedence: absolute (from/to) > keyword > relative.

    Args:
        relative_seconds: Look back this many seconds from now (0 = all time).
        keyword: Natural-language range, e.g. "last 24 hours".
        time_from: ISO-8601 start for an absolute range.
        time_to: ISO-8601 end for an absolute range.
    """
    if time_from and time_to:
        return {"type": "absolute", "from": time_from, "to": time_to}
    if keyword:
        return {"type": "keyword", "keyword": keyword}
    if relative_seconds is not None:
        return {"type": "relative", "range": relative_seconds}
    # Sensible default: last 15 minutes.
    return {"type": "relative", "range": 900}


def _rows_to_dicts(payload: dict) -> list[dict]:
    """Convert a scripting-API {schema, datarows} payload to a list of dicts."""
    schema = payload.get("schema", [])
    names = [col.get("field") or col.get("name") for col in schema]
    rows = payload.get("datarows", [])
    result = []
    for row in rows:
        result.append({names[i]: row[i] for i in range(min(len(names), len(row)))})
    return result


# -- Search & aggregation tools -------------------------------------------------


@mcp.tool()
def graylog_search_messages(
    query: str = "*",
    streams: list[str] | None = None,
    fields: list[str] | None = None,
    size: int = 50,
    relative_seconds: int | None = None,
    keyword: str | None = None,
    time_from: str | None = None,
    time_to: str | None = None,
    sort: str = "timestamp",
    sort_order: str = "desc",
) -> dict:
    """Search Graylog log messages with a Lucene query over a time range.

    Returns matching messages as a list of field->value dicts, most recent
    first by default. Always scope with a time range and, where possible, a
    stream to keep the query fast.

    Args:
        query: Lucene query string (e.g. 'http_response_code:500 AND source:web01').
            Use '*' to match everything.
        streams: Optional list of stream IDs to restrict the search to.
        fields: Fields to return per message. Defaults to timestamp, source, message.
        size: Maximum number of messages to return (default 50).
        relative_seconds: Look back this many seconds from now (0 = all time).
        keyword: Natural-language time range, e.g. "last 24 hours" or "yesterday".
        time_from: ISO-8601 start for an absolute range (used with time_to).
        time_to: ISO-8601 end for an absolute range (used with time_from).
        sort: Field to sort by (default 'timestamp').
        sort_order: 'asc' or 'desc' (default 'desc').
    """
    body: dict = {
        "query": query,
        "fields": fields or ["timestamp", "source", "message"],
        "size": size,
        "sort": sort,
        "sort_order": sort_order,
        "timerange": _build_timerange(
            relative_seconds, keyword, time_from, time_to
        ),
    }
    if streams:
        body["streams"] = streams

    payload = _request("POST", "search/messages", json_body=body)
    if not isinstance(payload, dict):
        return {"messages": [], "raw": payload}

    return {
        "messages": _rows_to_dicts(payload),
        "count": len(payload.get("datarows", [])),
        "effective_timerange": payload.get("metadata", {}).get(
            "effective_timerange"
        ),
    }


@mcp.tool()
def graylog_aggregate(
    group_by: list[str],
    metrics: list[str] | None = None,
    query: str = "*",
    streams: list[str] | None = None,
    relative_seconds: int | None = None,
    keyword: str | None = None,
    time_from: str | None = None,
    time_to: str | None = None,
) -> dict:
    """Aggregate/summarize Graylog log data grouped by one or more fields.

    Useful for questions like "top source IPs", "error counts per host", or
    "average response time by endpoint".

    Args:
        group_by: Fields to group by (e.g. ['source'] or ['http_method', 'source']).
        metrics: Metric specs as 'function:field' or just 'count'. Supported
            functions: count, avg, min, max, sum, stddev, variance, percentile,
            latest, sumofsquares. Defaults to ['count'].
        query: Lucene query to filter before aggregating. Defaults to '*'.
        streams: Optional list of stream IDs to restrict the aggregation to.
        relative_seconds: Look back this many seconds from now (0 = all time).
        keyword: Natural-language time range, e.g. "last 24 hours".
        time_from: ISO-8601 start for an absolute range (used with time_to).
        time_to: ISO-8601 end for an absolute range (used with time_from).
    """
    metric_specs = metrics or ["count"]
    parsed_metrics = []
    for spec in metric_specs:
        if ":" in spec:
            func, _, field = spec.partition(":")
            parsed_metrics.append({"function": func.strip(), "field": field.strip()})
        else:
            parsed_metrics.append({"function": spec.strip()})

    body: dict = {
        "query": query,
        "group_by": [{"field": f} for f in group_by],
        "metrics": parsed_metrics,
        "timerange": _build_timerange(
            relative_seconds, keyword, time_from, time_to
        ),
    }
    if streams:
        body["streams"] = streams

    payload = _request("POST", "search/aggregate", json_body=body)
    if not isinstance(payload, dict):
        return {"results": [], "raw": payload}

    return {
        "results": _rows_to_dicts(payload),
        "effective_timerange": payload.get("metadata", {}).get(
            "effective_timerange"
        ),
    }


@mcp.tool()
def graylog_list_fields(limit: int = 200) -> list[dict]:
    """List available message field names and metadata for building queries.

    Args:
        limit: Maximum number of fields to return (default 200).
    """
    payload = _request("GET", "system/fields")
    fields = payload.get("fields", []) if isinstance(payload, dict) else []
    return [{"name": f} for f in sorted(fields)[:limit]]


# -- Streams, indices & inputs (read-only inspection) ---------------------------


@mcp.tool()
def graylog_list_streams(include_disabled: bool = False) -> list[dict]:
    """List log streams (data sources) with their IDs, titles, and status.

    Use the returned 'id' values to scope graylog_search_messages and
    graylog_aggregate calls.

    Args:
        include_disabled: If True, include disabled streams. Defaults to False.
    """
    payload = _request("GET", "streams")
    streams = payload.get("streams", []) if isinstance(payload, dict) else []
    result = []
    for stream in streams:
        if not include_disabled and stream.get("disabled"):
            continue
        result.append(
            {
                "id": stream.get("id"),
                "title": stream.get("title"),
                "description": stream.get("description"),
                "disabled": stream.get("disabled", False),
                "index_set_id": stream.get("index_set_id"),
            }
        )
    return result


@mcp.tool()
def graylog_get_stream(stream_id: str) -> dict:
    """Get details of a single stream by ID, including its routing rules.

    Args:
        stream_id: The stream ID (from graylog_list_streams).
    """
    stream = _request("GET", f"streams/{stream_id}")
    if not isinstance(stream, dict):
        return {"raw": stream}
    return {
        "id": stream.get("id"),
        "title": stream.get("title"),
        "description": stream.get("description"),
        "disabled": stream.get("disabled", False),
        "index_set_id": stream.get("index_set_id"),
        "matching_type": stream.get("matching_type"),
        "rules": stream.get("rules", []),
    }


@mcp.tool()
def graylog_list_index_sets() -> list[dict]:
    """List index sets with their rotation and retention configuration.

    Helps you understand data lifecycle and how long logs are retained.
    """
    payload = _request("GET", "system/indices/index_sets")
    index_sets = payload.get("index_sets", []) if isinstance(payload, dict) else []
    result = []
    for index_set in index_sets:
        result.append(
            {
                "id": index_set.get("id"),
                "title": index_set.get("title"),
                "index_prefix": index_set.get("index_prefix"),
                "rotation_strategy_class": index_set.get(
                    "rotation_strategy_class"
                ),
                "retention_strategy_class": index_set.get(
                    "retention_strategy_class"
                ),
                "writable": index_set.get("writable"),
                "default": index_set.get("default"),
            }
        )
    return result


@mcp.tool()
def graylog_list_inputs() -> list[dict]:
    """List configured log inputs (syslog, GELF, Beats, etc.) and their state.

    Useful for checking ingestion health and where data comes from.
    """
    payload = _request("GET", "system/inputs")
    inputs = payload.get("inputs", []) if isinstance(payload, dict) else []
    result = []
    for item in inputs:
        message_input = item.get("message_input", item)
        result.append(
            {
                "id": message_input.get("id"),
                "title": message_input.get("title"),
                "type": message_input.get("type"),
                "global": message_input.get("global"),
                "node": message_input.get("node"),
            }
        )
    return result


# -- System information ---------------------------------------------------------


@mcp.tool()
def graylog_system_status() -> dict:
    """Return basic system information about the Graylog installation.

    Includes cluster ID, version, hostname, timezone, and operating system.
    Good first call to confirm which environment you are connected to.
    """
    data = _request("GET", "system")
    if not isinstance(data, dict):
        return {"raw": data}
    return {
        "cluster_id": data.get("cluster_id"),
        "node_id": data.get("node_id"),
        "version": data.get("version"),
        "hostname": data.get("hostname"),
        "timezone": data.get("timezone"),
        "operating_system": data.get("operating_system"),
        "lifecycle": data.get("lifecycle"),
        "is_processing": data.get("is_processing"),
        "started_at": data.get("started_at"),
    }


if __name__ == "__main__":
    mcp.run()

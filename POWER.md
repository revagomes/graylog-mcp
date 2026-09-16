---
name: "graylog-mcp"
displayName: "Graylog"
description: "Search, aggregate, and inspect logs from a self-hosted Graylog instance via a local MCP server. Wraps the Graylog REST API (search scripting, streams, index sets, inputs, system status) behind clean read-only tools so an LLM can query logs without hand-crafting Lucene queries, time ranges, or URL encoding."
keywords: ["graylog", "logs", "log search", "lucene", "aggregation", "streams", "observability", "siem", "rest api", "mcp", "troubleshooting", "incident"]
author: "Renato Vasconcellos Gomes"
---

# Graylog

## Overview

This Power provides a **local MCP server** that connects to a self-hosted Graylog instance
(default: `https://graylog.example.com`) through its REST API. It lets an LLM search
logs, summarize trends, and orient itself in the environment using clean tool interfaces.

Rather than depending on Graylog's experimental built-in MCP endpoint, this power runs a small
FastMCP server on your machine that talks to the stable Graylog REST API — specifically the
**search scripting API** (`/api/search/messages`, `/api/search/aggregate`) plus read-only
system, stream, index, and input inspection endpoints.

**Key capabilities:**

- **Message search** — Run Lucene queries over a time range, scoped by stream, with field selection
- **Aggregation** — Summarize trends: top sources, error counts per host, averages by field
- **Stream discovery** — List and inspect streams to scope searches correctly
- **Data lifecycle** — Inspect index sets (rotation/retention) and indices
- **Ingestion health** — List configured inputs and their state
- **Environment orientation** — Confirm version, cluster, timezone via system status

All operations are **read-only**.

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| **Python 3.11+** | Required for the MCP server |
| **uvx** | Runs the FastMCP server (part of the `uv` toolchain) |
| **Graylog access token** | REST API access token from your Graylog user (see README) |
| **Network access** | The machine must reach the Graylog instance over HTTPS |

No username/password is sent. Authentication uses a REST API access token per Graylog convention:
the token is the HTTP Basic *username* and the literal string `token` is the *password*.

## Configuration

All configuration is via environment variables set in `mcp.json`:

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `GRAYLOG_URL` | No | `https://graylog.example.com` | Base URL of the Graylog instance |
| `GRAYLOG_TOKEN` | **Yes** | _(none)_ | REST API access token |
| `GRAYLOG_VERIFY_TLS` | No | `true` | Set `false` only for internal-CA instances |
| `GRAYLOG_TIMEOUT` | No | `30` | Per-request timeout in seconds |

## Available MCP Tools

| Tool | Purpose |
|------|---------|
| `graylog_search_messages` | Search log messages with a Lucene query over a time range |
| `graylog_aggregate` | Group/summarize log data (count, avg, min, max, top values) |
| `graylog_list_fields` | List available field names for building queries |
| `graylog_list_streams` | List log streams (data sources) with IDs and status |
| `graylog_get_stream` | Get details and routing rules of a single stream |
| `graylog_list_index_sets` | List index sets with rotation/retention policies |
| `graylog_list_inputs` | List configured inputs and their ingestion state |
| `graylog_system_status` | Return version, cluster, timezone, OS of the instance |

## Time Ranges

Search and aggregation tools accept flexible, mutually-exclusive time inputs (precedence:
absolute > keyword > relative; default: last 15 minutes):

- `relative_seconds` — look back N seconds from now (`0` = all time)
- `keyword` — natural language, e.g. `"last 24 hours"`, `"yesterday"`
- `time_from` / `time_to` — ISO-8601 absolute range

## Activation Keywords

This power activates when you mention:
- graylog, logs, log search, search logs
- lucene, query logs, aggregate logs
- streams, index set, retention, inputs, ingestion
- error rate, top sources, failed logins, troubleshoot, incident

## Quick Usage Examples

### Orient yourself

User: "What Graylog am I connected to and what streams exist?"
→ Call `graylog_system_status()` then `graylog_list_streams()`.

### Search for errors

User: "Show 500 errors on the web stream in the last hour"
→ Call `graylog_list_streams()` to find the stream ID, then
`graylog_search_messages(query="http_response_code:500", streams=["<id>"], keyword="last 1 hour")`.

### Summarize a trend

User: "Top 10 source IPs with failed SSH logins over the last 24 hours"
→ Call `graylog_aggregate(group_by=["source"], metrics=["count"], query="sshd AND \"Failed password\"", keyword="last 24 hours")`
and present the top rows.

### Check retention

User: "How long are logs kept?"
→ Call `graylog_list_index_sets()` and summarize rotation/retention per set.

## Why This Exists

Graylog's REST API is powerful but awkward to call by hand: searches require building JSON
timerange objects, choosing between relative/absolute/keyword ranges, URL-encoding, and setting
the `X-Requested-By` header. This power wraps that complexity into a handful of tool calls, and
keeps everything read-only so it is safe to point at a production log store.

## Troubleshooting

### Authentication failed (401)

The `GRAYLOG_TOKEN` is missing, invalid, or expired. Create a new REST API access token in
Graylog (user menu → **Edit tokens**) and update the env in `mcp.json`.

### Permission denied (403)

The token's user lacks permission for the requested resource. Grant the user the required role,
or use a dedicated read-only Graylog user for MCP access.

### TLS verification failed

If the instance uses an internal/enterprise CA, set `GRAYLOG_VERIFY_TLS=false` in the env. Prefer
installing the CA certificate over disabling verification where possible.

### Empty results

Widen the time range (`keyword="last 24 hours"`), relax the Lucene query to `*`, and confirm the
stream ID with `graylog_list_streams`. Remember the default range is only the last 15 minutes.

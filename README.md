# graylog-mcp

A Kiro Power that runs a **local MCP server** for querying a self-hosted
[Graylog](https://graylog.org) instance via its REST API.

You point it at your own Graylog instance with the `GRAYLOG_URL` environment variable.

## Problem

Graylog's REST API is capable but tedious to drive by hand. Searches require building JSON
time-range objects, picking between relative/absolute/keyword ranges, URL-encoding parameters,
and setting the `X-Requested-By` header on every call. Graylog also ships an *experimental*
built-in MCP endpoint, but it may change without notice and is discouraged for production use.

## Solution

This power runs a small [FastMCP](https://github.com/jlowin/fastmcp) server on your machine that
wraps the **stable** Graylog REST API behind clean, read-only tools. Authentication uses a
Graylog REST API access token — no username/password is sent, and nothing is written back to
Graylog.

## Tools

| Tool | Description |
|------|-------------|
| `graylog_search_messages` | Search log messages with a Lucene query over a time range |
| `graylog_aggregate` | Group/summarize log data (count, avg, min, max, top values) |
| `graylog_list_fields` | List available field names for building queries |
| `graylog_list_streams` | List log streams (data sources) with IDs and status |
| `graylog_get_stream` | Get details and routing rules of a single stream |
| `graylog_list_index_sets` | List index sets with rotation/retention policies |
| `graylog_list_inputs` | List configured inputs and their ingestion state |
| `graylog_system_status` | Return version, cluster, timezone, OS of the instance |

## Setup

### 1. Create a Graylog REST API access token

1. Log in to Graylog.
2. Open the user menu (top right) → **Edit tokens** (or **System → Users → your user → Edit tokens**).
3. Create a token, give it a name (e.g. `kiro-mcp`), and copy the generated value.

> Prefer a dedicated **read-only** Graylog user for MCP access so the token can only read logs.

Per Graylog convention the token is used as the HTTP Basic **username**, with the literal
string `token` as the **password**. The server handles this for you.

### 2. Ensure `uvx` is installed

```bash
uvx --version   # part of the uv toolchain: https://docs.astral.sh/uv/
```

### 3. Add to your `.kiro/settings/mcp.json`

```json
{
  "mcpServers": {
    "graylog": {
      "command": "uvx",
      "args": ["--from", "fastmcp", "--with", "requests", "fastmcp", "run", "/path/to/graylog-mcp/server/graylog_mcp.py"],
      "env": {
        "GRAYLOG_URL": "https://graylog.example.com",
        "GRAYLOG_TOKEN": "your-access-token-here",
        "GRAYLOG_VERIFY_TLS": "true",
        "GRAYLOG_TIMEOUT": "30"
      },
      "disabled": false
    }
  }
}
```

Replace `/path/to/graylog-mcp` with the absolute path to this directory, set
`GRAYLOG_URL` to your Graylog instance base URL, and set `GRAYLOG_TOKEN` to the token
from step 1. You can also inject the token from your shell environment with
`"GRAYLOG_TOKEN": "${env:GRAYLOG_TOKEN}"` to keep it out of the config file.

## Configuration

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `GRAYLOG_URL` | **Yes** | _(none)_ | Base URL of the Graylog instance, e.g. `https://graylog.example.com` |
| `GRAYLOG_TOKEN` | **Yes** | _(none)_ | REST API access token |
| `GRAYLOG_VERIFY_TLS` | No | `true` | Set `false` only for internal-CA instances |
| `GRAYLOG_TIMEOUT` | No | `30` | Per-request timeout in seconds |

## Usage Examples

- "What version of Graylog am I connected to?" → `graylog_system_status`
- "What streams can I search?" → `graylog_list_streams`
- "Show 500 errors in the last hour" → `graylog_search_messages`
- "Top 10 source IPs with failed SSH logins over 24h" → `graylog_aggregate`
- "How long are logs retained?" → `graylog_list_index_sets`

## Security Notes

- All tools are **read-only** — the server never writes to Graylog.
- The token is only sent to `GRAYLOG_URL` over HTTPS; keep it out of version control.
- Point the server only at Graylog instances you are authorized to query.

## License

GPLv2+ — see [LICENSE](LICENSE) for the full text.

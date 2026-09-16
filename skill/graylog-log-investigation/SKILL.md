---
name: graylog-log-investigation
description: Investigate application logs, errors, and trends in Graylog through the graylog MCP server. Use when the user asks to search logs, find errors/exceptions, check what is failing in an environment (prod/acc/dev), summarize log trends, trace an incident, or answer questions about a running application's behavior from its logs. Covers Lucene query construction, environment/stream scoping, aggregation, and the gotchas of Drupal-on-Apache log formats.
metadata:
  author: Renato Vasconcellos Gomes
  version: "1.0"
---

# Graylog Log Investigation

Turn questions about a running application ("what's erroring on ACC?", "top failing endpoints", "did the deploy break anything?") into correct Graylog MCP calls. This skill encodes how to scope, query, aggregate, and read logs through the `graylog` MCP server — including the non-obvious gotchas that otherwise produce empty or misleading results.

## When to Use

Trigger this skill when the user wants to:

- **Find errors** — "PHP errors on ACC", "what's failing in prod", "show exceptions in the last 2 days"
- **Search logs** — "search the logs for X", "find requests to /path", "logs for this user/IP"
- **Summarize trends** — "top error types", "busiest sources", "error rate over time", "top source IPs"
- **Investigate an incident** — "what happened around 14:00", "did the deploy cause errors", "trace this failure"
- **Orient** — "what streams/environments exist", "what Graylog am I connected to"

**Trigger phrases:** "graylog", "check the logs", "search logs", "php errors", "exceptions", "what's failing", "error rate", "top errors", "log trends", "investigate incident", "prod logs", "acc logs".

If the `graylog` MCP tools are not available, tell the user to configure the graylog-mcp power (see its README) and stop — do not fabricate log data.

---

## The 8 Tools

| Tool | Use for |
|------|---------|
| `graylog_search_messages` | Fetch actual log messages matching a Lucene query over a time range |
| `graylog_aggregate` | Summarize: counts/avg/min/max/sum grouped by field(s) |
| `graylog_list_streams` | Discover data sources and their stream IDs (needed to scope) |
| `graylog_get_stream` | Inspect one stream's routing rules |
| `graylog_list_fields` | List available field names |
| `graylog_list_inputs` | List log inputs (ingestion health) |
| `graylog_list_index_sets` | Rotation/retention config (may be empty without admin perms) |
| `graylog_system_status` | Version, cluster, timezone — good first orientation call |

---

## The Investigation Loop

1. **Orient (once per session):** `graylog_list_streams` to get stream IDs. `graylog_system_status` if you need version/timezone.
2. **Scope:** pick the stream ID for the relevant application, and decide the environment filter and time range.
3. **Aggregate first:** use `graylog_aggregate` to find the *shape* — which error types, which sources, when. Cheaper and more informative than dumping raw messages.
4. **Drill down:** use `graylog_search_messages` with a targeted query to read the actual errors, requesting `full_message` (see gotcha below).
5. **Report** with the effective time range (every response returns `effective_timerange`) so results are reproducible.

---

## Critical Gotchas (read before querying)

These are the difference between a correct answer and an empty/misleading one.

### 1. `full_message`, not `message`, for errors

`message` is **truncated (~250 chars)** by Apache's `proxy_fcgi` log line — it cuts off before the actual exception detail. The complete text (exception, file, line, stack context) lives in **`full_message`** (~1600 chars).

> Always request `fields=["timestamp", "full_message"]` when reading errors. Only use `message` for quick scans where truncation is acceptable.

### 2. Environment naming is inconsistent

The environment discriminator is the **`environment`** field, but values differ across applications:

- Some use `prod` / `acc`
- Some use `production` / `acceptance`
- Some use **all four**

Never assume one spelling. Filter for both, or check first with an aggregation:

```
# Discover the actual values in play
graylog_aggregate(group_by=["environment"], streams=["<id>"], keyword="last 7 days")

# Then filter defensively
query = '(environment:acc OR environment:acceptance) AND ...'
```

### 3. Drupal logs are plain text, not structured fields

Structured fields you might expect — `exception_class`, `exception_message`, `channel`, `SeverityText`, `backtrace`, `logger` — **are empty** for these Drupal-on-Apache logs. The logs arrive as raw Apache/`proxy_fcgi` text.

> **You cannot group_by or filter on `exception_class`.** Instead use **text search** on `full_message`: `query='"php.ERROR"'` to find PHP errors, and add `AND "ParamNotConvertedException"` (quote the class name) to filter by type. To summarize error types, fetch messages and parse the exception class out of `full_message` yourself.

### 4. `level` is syslog level, not error severity

`level` is the syslog priority (e.g. `6` = info). It does **not** cleanly separate application errors. Detect PHP errors by the text marker `"php.ERROR"`, not by `level`.

### 5. Auth cookie is short-lived

This instance sits behind an SSO/OAuth2 proxy; the MCP authenticates with a browser session cookie (`GRAYLOG_COOKIE`). When it expires, tools return an "SSO/OAuth2 reverse proxy… redirected to a sign-in page" error. The fix is **not** a code change — re-export the cookie from the browser into the env. Tell the user this plainly rather than retrying.

### 6. `list_index_sets` may be empty

Returns `total: 0` if the connected user lacks admin permission. That's a permissions fact, not a bug — don't treat it as "no retention configured."

---

## Lucene Query Cookbook

Queries go in the `query` argument. Combine with `streams`, a time range, and `fields`.

| Goal | `query` |
|------|---------|
| Everything | `*` |
| All PHP errors | `"php.ERROR"` |
| Specific exception | `"php.ERROR" AND "ParamNotConvertedException"` |
| Errors in acceptance (defensive) | `(environment:acc OR environment:acceptance) AND "php.ERROR"` |
| From one source | `source:drupal` |
| HTTP 5xx (when a status field exists) | `http_response_code:[500 TO 599]` |
| Field exists | `_exists_:client_ip` |
| Phrase match | `"Failed password"` |
| Boolean | `source:apache AND NOT "php.ERROR"` |

For a Drupal-on-Apache stack, sources within a stream commonly include `varnish`, `apache`, `drupal`, `php-fpm`, `database`, `mails`. PHP application errors are almost always `source:drupal` (or `apache`). Confirm the sources present with `graylog_aggregate(group_by=["source"], ...)`.

---

## Time Ranges

Pass exactly one style (precedence: absolute > keyword > relative; default if none: last 15 min).

- `keyword="last 24 hours"`, `keyword="last 2 days"`, `keyword="yesterday"` — preferred for human phrasing
- `relative_seconds=3600` — precise look-back (0 = all time)
- `time_from="2026-09-14T00:00:00Z", time_to="2026-09-16T00:00:00Z"` — incident windows

Every response echoes `effective_timerange` — cite it when reporting.

---

## Aggregation

`graylog_aggregate(group_by=[...], metrics=[...], query=..., streams=[...], <timerange>)`

- `metrics` are `"function:field"` or bare `"count"`. Functions: `count`, `avg`, `min`, `max`, `sum`, `stddev`, `variance`, `percentile`, `latest`, `sumofsquares`.
- Group by a **populated** field. `source` and `environment` are reliable here; `exception_class` is not (see gotcha 3).
- Results come back as a list of dicts; the count column is named `metric: count()`.

Examples:

```
# Which sources are noisiest (last 24h)
graylog_aggregate(group_by=["source"], metrics=["count"], streams=["<id>"], keyword="last 24 hours")

# PHP error volume per source in acceptance
graylog_aggregate(group_by=["source"], metrics=["count"],
                  query='(environment:acc OR environment:acceptance) AND "php.ERROR"',
                  streams=["<id>"], keyword="last 2 days")
```

To summarize **error types** (since `exception_class` is empty), fetch `full_message` for the matching errors and parse the class with a regex like `php\.ERROR:\s*([\w\\]+(?:Exception|Error))`, then count client-side.

---

## Worked Example: "PHP errors on ACC in the last 2 days"

1. `graylog_list_streams` → find the app's stream ID.
2. Confirm env spelling: `graylog_aggregate(group_by=["environment"], streams=["<id>"], keyword="last 2 days")`.
3. Count by source:
   `graylog_aggregate(group_by=["source"], metrics=["count"], query='(environment:acc OR environment:acceptance) AND "php.ERROR"', streams=["<id>"], keyword="last 2 days")`
4. Read the errors with full detail:
   `graylog_search_messages(query='(environment:acc OR environment:acceptance) AND "php.ERROR"', streams=["<id>"], keyword="last 2 days", size=60, fields=["timestamp","full_message"])`
5. Parse exception classes from `full_message`, group, and report counts + a representative full detail (class, reason, file:line) per type — plus the effective time range.

---

## Discovering Your Instance

This skill is deliberately generic. The concrete details of a given Graylog deployment —
which streams exist, their IDs, and how environments are named — should come from a
**project-scoped skill** or from live discovery, never be assumed.

To learn an instance at the start of an investigation:

1. `graylog_list_streams` — get the stream titles and IDs for each application.
2. For the relevant stream, confirm environment values:
   `graylog_aggregate(group_by=["environment"], streams=["<id>"], keyword="last 7 days")`
3. Confirm the sources present:
   `graylog_aggregate(group_by=["source"], streams=["<id>"], keyword="last 24 hours")`

Record these in a project-scoped skill (e.g. `.kiro/skills/graylog-<project>/SKILL.md`)
so the stream ID and environment spelling are captured privately for that project, while
this generic skill supplies the technique. Keep instance-specific identifiers out of any
public/shared location.

---

## Reporting Guidance

- Lead with the shape (counts by type/source), then representative details.
- Distinguish **actionable bugs** (TypeError, missing class, DB constraint) from **request noise** (e.g. `ParamNotConvertedException` on `/node/{node}` is usually bad links/bots, not a regression).
- Always state the stream, environment filter, and effective time range searched.
- If results are empty, widen the range and relax the query to `*` before concluding "nothing there" — and double-check the environment spelling.
- Never invent log lines. If a tool errors (e.g. expired cookie), report the error and the fix.

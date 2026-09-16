---
inclusion: auto
name: "Graylog Search Workflow"
description: "How to search, aggregate, and investigate logs in Graylog through the graylog MCP tools — scoping, time ranges, and Lucene query patterns."
---

# Graylog Search Workflow

Use the `graylog` MCP tools for any log investigation against the Graylog instance.
All tools are read-only.

## Orient Before You Search

1. `graylog_system_status` — confirm which environment you are connected to.
2. `graylog_list_streams` — find the stream ID(s) relevant to the question.
3. `graylog_list_fields` — confirm field names before building a query (avoids typos).

## Scope Every Search

A good search always sets:
- **A time range** — never rely on the 15-minute default for real investigations.
  - Prefer `keyword` for human phrasing: `"last 24 hours"`, `"yesterday"`.
  - Use `relative_seconds` for precise windows; `time_from`/`time_to` for incident windows.
- **A stream** — pass `streams=["<id>"]` whenever the data source is known. Faster and cleaner.
- **Only the fields you need** — pass `fields=[...]` to keep responses small and readable.

## Lucene Query Patterns

- Match everything: `*`
- Field match: `http_response_code:500`
- Range: `http_response_code:[500 TO 599]`
- Boolean: `source:web01 AND level:3`
- Phrase: `"Failed password"`
- Existence: `_exists_:user_id`

## Searching vs Aggregating

- Use `graylog_search_messages` when you need the **actual messages** (triage, root cause).
- Use `graylog_aggregate` when you need a **summary** (counts, top values, averages).
  - `group_by=["source"], metrics=["count"]` → top sources by volume.
  - `group_by=["endpoint"], metrics=["avg:took_ms"]` → average latency per endpoint.
  - Metrics are `function:field` or bare `count`. Functions: count, avg, min, max, sum,
    stddev, variance, percentile, latest, sumofsquares.

## Investigation Flow

1. Aggregate first to find the shape of the problem (which host, which error, when).
2. Narrow with a targeted `graylog_search_messages` on the identified stream/host/time window.
3. Report findings with the effective time range (returned in each response) so results are
   reproducible.

## Presenting Results

- Summarize the top findings; do not dump every raw row.
- Always state the time range and stream that were searched.
- If results are empty, widen the range and relax the query to `*` before concluding there is
  nothing there.

# graylog-log-investigation (skill)

A Kiro skill that teaches an AI agent how to investigate application logs, errors,
and trends in Graylog through the [graylog-mcp](../../README.md) MCP server.

It captures the practical knowledge that turns a vague request ("what's erroring on
ACC?") into correct MCP calls — Lucene query construction, environment/stream scoping,
aggregation patterns, and the non-obvious gotchas (truncated `message` vs `full_message`,
inconsistent `environment` values, unstructured Drupal-on-Apache logs, short-lived SSO
cookie) that otherwise produce empty or misleading answers.

## Prerequisite

The `graylog` MCP server must be configured and reachable — see the
[graylog-mcp README](../../README.md). The skill drives those tools; it does not talk to
Graylog directly.

## Install

### Kiro CLI / Kiro IDE

```bash
mkdir -p ~/.kiro/skills/graylog-log-investigation
cp SKILL.md ~/.kiro/skills/graylog-log-investigation/SKILL.md
```

Or per-project:

```bash
mkdir -p .kiro/skills/graylog-log-investigation
cp SKILL.md .kiro/skills/graylog-log-investigation/SKILL.md
```

### Other tools (Cursor, Claude Code, Cline, …)

`SKILL.md` is plain Markdown with YAML frontmatter. Paste its body into your tool's
custom-instructions / rules file. The `description` in the frontmatter is what a
skill-aware agent uses to decide when to activate it.

## Usage

Once installed, trigger it by asking things like:

> "check graylog for php errors on acc", "top error types in prod last 24h",
> "search the logs for this exception", "what streams exist", "did the deploy break anything"

The agent will orient (list streams), scope (stream + environment + time range),
aggregate to find the shape, then drill into `full_message` for detail — and report with
the effective time range.

## Instance-specific details stay private

This skill is intentionally **generic** — it teaches the investigation technique and the
transferable gotchas, and contains **no** stream IDs, project names, or hostnames.

Concrete details of a given deployment (which streams exist, their IDs, how environments
are spelled) belong in a **project-scoped skill** kept in that project's private repo, e.g.
`.kiro/skills/graylog-<project>/SKILL.md`. Such a skill references this one for technique
and adds only the private facts. Never put instance identifiers in this public skill.

## License

GPLv2+ — see the [repository LICENSE](../../LICENSE).

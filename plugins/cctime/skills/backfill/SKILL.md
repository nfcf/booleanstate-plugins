---
description: Backfill cctime from existing Claude Code transcripts so past weeks show up in the report
argument-hint: "[since YYYY-MM-DD] [dry run]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cctime_backfill.py:*)
disable-model-invocation: true
---
Backfill cctime from my Claude Code transcripts with `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cctime_backfill.py`. Run nothing else.

My input: "$ARGUMENTS"
- "since <date>" -> `--since YYYY-MM-DD` ; "dry run"/"dry-run"/"preview" -> `--dry-run`

Run it once and show the output in a code block. Then, in at most three short lines, explain:
it wrote `backfill.jsonl` in the cctime data folder (delete it to undo; running again replaces it), sessions already
logged by the hooks were skipped, and subagent time is not backfilled. Suggest `/cctime:setup` to map folders to
clients and `/cctime:report last month` to see the result.

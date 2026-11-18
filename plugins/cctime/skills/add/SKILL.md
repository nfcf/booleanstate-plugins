---
description: Add manual time (meetings, calls, work outside Claude Code) to cctime, by range or duration; list or undo entries
argument-hint: "<today|yesterday|YYYY-MM-DD> <project> <HH:MM-HH:MM | 45m | 1h30> [note]  |  list [N]  |  undo"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cctime_add.py:*)
model: haiku
disable-model-invocation: true
---
Manage manual time entries in cctime with `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cctime_add.py`. Run nothing else.

My input: "$ARGUMENTS"

- "list" or "list N" -> run with `--list` or `--list N` and show the output in a code block.
- "undo" -> run with `--undo` and show its one-line output.
- Otherwise parse: date (today/hoje, yesterday/ontem, or YYYY-MM-DD; default today), project name, and either
  a time range (24h; "14h-14h45" means 14:00 to 14:45) or a duration (45m, 1h, 1h30, 1.5h), and an optional note.
  A duration ends now, unless I give an end time ("1h ending 12:00") or a start time ("1h from 9:00").
  If the project or the time is missing or ambiguous, ask me instead of guessing.
  Run exactly once, one of:
  `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cctime_add.py --date <date> --project "<project>" --start <HH:MM> --end <HH:MM> --note "<note>"`
  `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cctime_add.py --date <date> --project "<project>" --duration <dur> [--end <HH:MM> | --start <HH:MM>] --note "<note>"`
  If it fails with "Unknown project", show me the known names it printed and ask which one I meant
  (a misspelt name becomes a separate row in the report). Only if I confirm it is a new client, run the same
  command again with `--new-project`.

Show the script's output. No other commentary.

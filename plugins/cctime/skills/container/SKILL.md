---
description: Set up cctime logging for Claude Code running inside a dev container for a repo
argument-hint: "<path to repo on this machine> | list"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cctime_container.py:*)
disable-model-invocation: true
---
Set up cctime for a dev container with `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cctime_container.py`. Run nothing else.

My input: "$ARGUMENTS"
- "list" or empty -> run with `--list`.
- otherwise it is a repo path on this machine (the folder that is bind-mounted into the container):
  run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cctime_container.py "<path>"` once. If no path is given, ask for it.

Show the output in a code block. Then tell me the one command to run inside the container (as printed),
that I need to restart Claude Code in the container afterwards, and that the logger stores only times, session
ids and branch names, never prompt text.

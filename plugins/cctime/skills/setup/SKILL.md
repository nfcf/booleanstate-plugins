---
description: Map project folders to client names for cctime (writes projects.json after confirmation)
argument-hint: "[days, default 90]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cctime_setup.py:*)
disable-model-invocation: true
---
Help me map folders to clients in cctime's `projects.json`. Use only `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cctime_setup.py`.

1. Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cctime_setup.py list` (add `--days N` if I gave a number: "$ARGUMENTS").
   It prints JSON: `unmapped` folders with their time (minutes) in the period and git top-level,
   `current_rules`, existing `clients`, and `suggested_parent_rules` (a parent folder holding several unmapped folders).
2. If nothing is unmapped, say so and show the current rules as a short table. Then run
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cctime_setup.py diff`: if it lists past events to relabel or worktree
   events to record a main checkout on, show that, ask "Update these past events?", and only after a clear yes
   run the same command with `apply`. Then stop.
3. Otherwise show the unmapped folders as a table (folder, time as XhYY, logged as). Then ask me, in one message,
   which client each folder belongs to. Offer the existing client names, and offer each suggested parent rule as
   a single choice ("all of ~/Repos/client-b -> one client"). I may skip folders that are not client work.
   Rules are folder prefixes; the longest matching prefix wins. If I skip every folder, handle relabelling as in
   step 2 and stop.
4. Build a JSON object of new rules `{"<folder prefix>": "<client>"}` from my answers (use `~/` paths as listed).
   Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cctime_setup.py diff --rules '<json>'` and show me the diff and
   the list of past events it would relabel.
5. Ask "Write this to projects.json and relabel past events?" and wait. Only after a clear yes, run the same
   command with `apply` instead of `diff`. It backs up projects.json and each event log it rewrites first.
6. Tell me what was written and relabelled. Reports now show past time under the new mapping without `remap`.

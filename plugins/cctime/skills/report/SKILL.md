---
description: Time per project from Claude Code sessions (cctime). Default this week. Use when the user asks how much time they spent per project or client, or wants a timesheet.
argument-hint: "[today | yesterday | last week | this month | last month | <from> <to>] [round 15] [csv <file>] [remap]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cctime_report.py:*)
model: haiku
---
Run the cctime report and show it to me.

My request: "$ARGUMENTS"

Turn my request into flags for `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cctime_report.py` (do not run anything else):
- empty -> no flags (this week)
- "today"/"hoje" -> --today ; "yesterday"/"ontem" -> --yesterday ; "last week"/"semana passada" -> --last-week
- "this month"/"este mês" -> --this-month ; "last month"/"mês passado" -> --last-month
- a month name or two dates -> --from YYYY-MM-DD --to YYYY-MM-DD (current year unless given)
- "round N" -> --round N ; "csv <path>" -> --csv <path>
- "remap" -> --remap (re-resolve projects with the current folder mapping)

Run it once, then show the output exactly as printed, in a code block. After it, add at most two short lines:
which project took most time, and the parallel overlap if it is above zero. No other commentary.

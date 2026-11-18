#!/bin/sh
# cctime logger for Claude Code running inside a dev container.
# Pure POSIX sh (no python/jq needed). Writes next to itself, i.e. into the bind-mounted repo,
# so the Mac can read it. Stores only time, event, session, branch - never your prompt text.
in=$(cat)
val() { printf '%s' "$in" | grep -o "\"$1\" *: *\"[^\"]*\"" | head -1 | sed 's/.*"\([^"]*\)"$/\1/'; }
ev=$(val hook_event_name); sid=$(val session_id); aid=$(val agent_id); aty=$(val agent_type)
dir="${CLAUDE_PROJECT_DIR:-$(pwd)}"
br=$(git -C "$dir" rev-parse --abbrev-ref HEAD 2>/dev/null)
ts=$(date -u +%Y-%m-%dT%H:%M:%S+00:00)
printf '{"ts":"%s","event":"%s","session":"%s","agent_id":"%s","agent_type":"%s","branch":"%s","cwd":"%s","host":"%s"}\n' \
  "$ts" "$ev" "$sid" "$aid" "$aty" "$br" "$dir" "$(hostname 2>/dev/null)" >> "$(dirname "$0")/events.jsonl" 2>/dev/null
exit 0

#!/usr/bin/env python3
"""cctime hook logger: append one JSON line per Claude Code hook event to $CCTIME_HOME/events.jsonl.

Registered (async) for UserPromptSubmit, Stop, StopFailure, SessionStart, SessionEnd, SubagentStart, SubagentStop.
Never blocks or fails Claude Code: any error is swallowed. Stores no prompt text.
"""
import json, os, socket, sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    import cctime_common as c
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    cwd = data.get('cwd') or os.getcwd()
    branch = c.git(cwd, 'rev-parse', '--abbrev-ref', 'HEAD')
    rec = {
        'ts': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'event': data.get('hook_event_name'),
        'session': data.get('session_id'),
        'cwd': cwd,
        'project': c.resolve_cwd(cwd, c.load_rules()),
        'branch': branch or None,
        'ticket': c.ticket_for(branch),
        'host': socket.gethostname(),
    }
    for k in ('source', 'reason', 'agent_id', 'agent_type'):
        if data.get(k):
            rec[k] = data[k]
    os.makedirs(c.HOME, exist_ok=True)
    with open(c.EVENTS, 'a') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        pass
    sys.exit(0)

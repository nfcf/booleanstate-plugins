#!/usr/bin/env python3
"""Backfill cctime from existing Claude Code transcripts, so past weeks show up in the report.

Reads ~/.claude/projects/*/*.jsonl (or $CLAUDE_CONFIG_DIR/projects) and writes synthesized events to
$CCTIME_HOME/backfill.jsonl (delete that file to undo; re-running replaces it):
  UserPromptSubmit at each real prompt you typed,
  Stop at the last assistant message before the next prompt (or the end of the transcript).
Never duplicates hook data: sessions already in events.jsonl or a dev-container log are skipped, and only
events older than the first hook event are written. Subagent (sidechain) activity is not backfilled.
No prompt text is read into the output.

  cctime_backfill.py [--since YYYY-MM-DD] [--dry-run]
"""
import argparse, glob, json, os, sys
from collections import defaultdict
from datetime import date, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cctime_common as c

SYNTHETIC_PREFIXES = ('<local-command-stdout', '<local-command-stderr', '<bash-stdout', '<bash-stderr',
                      '<task-notification', '[Request interrupted', 'Caveat: The messages below')


def is_real_prompt(r):
    """A line the user typed (or a slash command they ran), not a tool result, reminder, summary or notification."""
    if r.get('type') != 'user' or r.get('isSidechain') or r.get('isMeta') or r.get('isCompactSummary'):
        return False
    if r.get('isVisibleInTranscriptOnly') or r.get('toolUseResult') is not None:
        return False
    origin = r.get('origin')
    kind = origin.get('kind') if isinstance(origin, dict) else origin
    if kind not in (None, 'human'):                     # peer, task-notification, ... are not prompts
        return False
    content = (r.get('message') or {}).get('content')
    if isinstance(content, list):
        if any(isinstance(b, dict) and b.get('type') == 'tool_result' for b in content):
            return False
        texts = [b.get('text', '') for b in content if isinstance(b, dict) and b.get('type') == 'text']
        first = texts[0] if texts else ''
    elif isinstance(content, str):
        first = content
    else:
        return False
    return not first.lstrip().startswith(SYNTHETIC_PREFIXES)


def read_transcripts(root):
    """{session: [(ts, kind, cwd, branch)]} with kind 'prompt' or 'assistant', deduplicated by line uuid."""
    seen = set(); out = defaultdict(list)
    for path in glob.glob(os.path.join(root, '*', '*.jsonl')):
        try:
            f = open(path, encoding='utf-8', errors='replace')
        except OSError:
            continue
        with f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(r, dict) or r.get('type') not in ('user', 'assistant') or r.get('isSidechain'):
                    continue
                uid = r.get('uuid')
                if uid:
                    if uid in seen: continue
                    seen.add(uid)
                sid, ts = r.get('sessionId'), r.get('timestamp')
                if not sid or not ts: continue
                if r['type'] == 'user':
                    if not is_real_prompt(r): continue
                    kind = 'prompt'
                else:
                    kind = 'assistant'
                try:
                    t = c.parse_ts(ts)
                except ValueError:
                    continue
                out[sid].append((t, kind, r.get('cwd'), r.get('gitBranch')))
    return out


def hook_sessions_and_first_ts(events_path, repo_files):
    sessions = set(); first = None
    for path, is_main in [(events_path, True)] + [(f, False) for f in repo_files]:
        if not os.path.exists(path): continue
        with open(path) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get('session'): sessions.add(r['session'])
                if is_main and r.get('ts'):
                    try:
                        t = c.parse_ts(r['ts'])
                    except ValueError:
                        continue
                    first = t if first is None or t < first else first
    return sessions, first


def synthesize(sid, lines, rules, cutoff, since):
    """Events for one session: a prompt, then Stop at the last assistant line before the next prompt.
    A prompt Claude never answered (a local command such as /clear, or an instant interrupt) gets a Stop at its own
    time, so it adds no agent time."""
    lines.sort(key=lambda x: x[0])
    evs = []; open_run = False; last_assistant = None; last_prompt = None

    def emit(t, event, cwd, branch):
        if cutoff is not None and t >= cutoff: return
        if since is not None and t.astimezone().date() < since: return
        cwd = cwd or ''
        main = c.worktree_main(cwd) if cwd else None
        evs.append({'ts': t.astimezone(timezone.utc).isoformat(timespec='seconds'), 'event': event, 'session': sid,
                    'cwd': cwd, 'project': c.resolve_cwd(cwd, rules, main) if cwd else 'unknown',
                    'branch': branch or None, 'ticket': c.ticket_for(branch), 'source': 'backfill'})
        if main: evs[-1]['main'] = main

    for t, kind, cwd, branch in lines:
        if kind == 'prompt':
            if open_run: emit(*(last_assistant or last_prompt))
            emit(t, 'UserPromptSubmit', cwd, branch)
            open_run, last_assistant, last_prompt = True, None, (t, 'Stop', cwd, branch)
        elif open_run:
            last_assistant = (t, 'Stop', cwd, branch)
    if open_run: emit(*(last_assistant or last_prompt))
    return evs


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--since', help='only backfill from this date (YYYY-MM-DD)')
    ap.add_argument('--dry-run', action='store_true', help='show what would be written, write nothing')
    ap.add_argument('--transcripts', default=os.path.join(os.path.expanduser(os.environ.get('CLAUDE_CONFIG_DIR') or '~/.claude'), 'projects'))
    ap.add_argument('--out', default=c.BACKFILL)
    a = ap.parse_args(argv)
    since = date.fromisoformat(a.since) if a.since else None

    rules = c.load_rules()
    hook_sids, first_hook = hook_sessions_and_first_ts(c.EVENTS, c.repo_log_files())
    sessions = read_transcripts(a.transcripts)
    out = []; skipped = 0
    for sid, lines in sessions.items():
        if sid in hook_sids:
            skipped += 1; continue
        out.extend(synthesize(sid, lines, rules, first_hook, since))
    out.sort(key=lambda r: r['ts'])

    sids = {r['session'] for r in out}
    days = sorted({c.parse_ts(r['ts']).astimezone().date() for r in out})
    print(f'Transcripts: {len(sessions)} sessions in {a.transcripts}')
    print(f'Skipped {skipped} sessions already logged by hooks' +
          (f'; cut off at the first hook event ({first_hook.astimezone():%Y-%m-%d %H:%M})' if first_hook else ''))
    if out:
        print(f'Backfill: {len(sids)} sessions, {len(days)} days, {days[0]} .. {days[-1]}, {len(out)} events')
    else:
        print('Backfill: nothing to add.')
    if a.dry_run:
        print('Dry run: nothing written.'); return
    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    tmp = a.out + '.tmp'
    with open(tmp, 'w') as f:
        for r in out: f.write(json.dumps(r, ensure_ascii=False) + '\n')
    os.replace(tmp, a.out)
    print(f'Written: {c.tilde(a.out)} (delete it to undo; re-running replaces it)')


if __name__ == '__main__':
    main()

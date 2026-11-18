"""Shared paths and project resolution for cctime.

Every script takes its data dir from CCTIME_HOME (default ~/.cctime). Data never lives in the plugin folder,
so it survives plugin updates and uninstalls.
"""
import json, os, re, subprocess
from datetime import datetime

HOME = os.path.expanduser(os.environ.get('CCTIME_HOME') or '~/.cctime')
EVENTS = os.path.join(HOME, 'events.jsonl')        # written by the hook logger
BACKFILL = os.path.join(HOME, 'backfill.jsonl')    # written by cctime_backfill.py (delete to undo)
PROJECTS = os.path.join(HOME, 'projects.json')     # folder prefix -> client name
MANUAL = os.path.join(HOME, 'manual.csv')          # date,project,start,end,note
REPOS = os.path.join(HOME, 'repos.json')           # {"repos": [...]} repos with a dev-container logger
LEGACY_REPO_LOGS = os.path.expanduser('~/Repos/*/.cctime/events.jsonl')
TICKET = re.compile(r'[A-Z][A-Z0-9]+-\d+')


def ticket_for(branch):
    m = TICKET.search(branch or '')
    return m.group(0) if m else None


def git(cwd, *args):
    try:
        return subprocess.run(['git', '-C', cwd, *args], capture_output=True, text=True, timeout=2).stdout.strip()
    except Exception:
        return ''


def load_rules(path=None):
    """projects.json maps path prefixes to names, longest prefix wins:
       {"~/Repos/acme": "Acme", "~/Repos/client-b": "Client B"}"""
    try:
        with open(path or PROJECTS) as f:
            return {os.path.expanduser(k).rstrip('/'): v for k, v in json.load(f).items()}
    except Exception:
        return {}


def match_prefix(path, rules):
    for pre in sorted(rules, key=len, reverse=True):
        if path == pre or path.startswith(pre + '/'):
            return rules[pre]
    return None


def resolve(path, rules, top=None):
    """Prefix rule on `path`; else the folder name (git top-level if given), mapped by basename when a rule's
    folder has the same name (a dev container mounts the repo elsewhere, e.g. /workspaces/<name>)."""
    hit = match_prefix(path, rules)
    if hit is not None:
        return hit
    name = os.path.basename(top or path.rstrip('/')) or 'unknown'
    return {os.path.basename(k): v for k, v in rules.items()}.get(name, name)


_tops = {}
def git_top(cwd):
    """git top-level of cwd (cached), '' when not a repo or gone."""
    if cwd not in _tops:
        _tops[cwd] = git(cwd, 'rev-parse', '--show-toplevel') if cwd and os.path.isdir(cwd) else ''
    return _tops[cwd]


def resolve_cwd(cwd, rules):
    """What the logger records for an event in `cwd`."""
    hit = match_prefix(cwd, rules)
    return hit if hit is not None else resolve(cwd, rules, git_top(cwd))


def is_mapped(name, rules):
    return name in set(rules.values())


def parse_ts(s):
    """ISO timestamp -> aware datetime. Accepts 'Z' and any number of fraction digits (Python 3.9)."""
    s = s.strip().replace('Z', '+00:00')
    m = re.match(r'^(.*T\d\d:\d\d:\d\d)(\.\d+)?(.*)$', s)
    if m and m.group(2):
        s = m.group(1) + (m.group(2) + '000000')[:7] + m.group(3)
    return datetime.fromisoformat(s)


def repo_log_files():
    """Dev-container logs: repos registered in repos.json, or the legacy ~/Repos/* glob when it doesn't exist."""
    import glob
    if not os.path.exists(REPOS):
        return glob.glob(LEGACY_REPO_LOGS)
    out = []
    for r in load_repos():
        f = os.path.join(r, '.cctime', 'events.jsonl')
        if os.path.exists(f):
            out.append(f)
    return out


def load_repos():
    try:
        with open(REPOS) as f:
            data = json.load(f)
        return [os.path.expanduser(r).rstrip('/') for r in data.get('repos', [])]
    except Exception:
        return []


def tilde(path):
    h = os.path.expanduser('~')
    return '~' + path[len(h):] if path == h or path.startswith(h + '/') else path

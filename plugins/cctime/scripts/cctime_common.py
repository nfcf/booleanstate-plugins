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
        env = {k: v for k, v in os.environ.items()                # an inherited GIT_DIR would answer for every cwd
               if k not in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_COMMON_DIR', 'GIT_INDEX_FILE')}
        return subprocess.run(['git', '-C', cwd, *args], capture_output=True, text=True, timeout=2, env=env).stdout.strip()
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


def longest_prefix(path, rules):
    """The longest rule folder that is `path` or one of its parents, else None."""
    return next((pre for pre in sorted(rules, key=len, reverse=True) if path == pre or path.startswith(pre + '/')), None)


def match_prefix(path, rules):
    pre = longest_prefix(path, rules)
    return rules[pre] if pre is not None else None


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


_mains = {}
def git_main(cwd):
    """Main checkout of the repo cwd is in (cached), '' when not a repo or gone. For a linked worktree such as
    ~/Repos/app-MS-1 this is ~/Repos/app. Given in cwd's form (git reports real paths), so a checkout reached through
    a symlink still matches cwd and the rules."""
    if cwd not in _mains:
        common = git(cwd, 'rev-parse', '--git-common-dir') if cwd and os.path.isdir(cwd) else ''
        main = ''
        if common and '\n' not in common and os.path.basename(common) == '.git':  # not a submodule or bare repo
            real_cwd = os.path.realpath(cwd)
            real = os.path.normpath(os.path.join(real_cwd, common))            # git answers in real paths
            main = os.path.dirname(os.path.normpath(os.path.join(cwd, os.path.relpath(real, real_cwd))))
            try:
                same = os.path.samefile(os.path.join(main, '.git'), real)
            except OSError:
                same = False
            if not same:                                                     # a symlink below the shared folder
                main = os.path.dirname(real)
        _mains[cwd] = main
    return _mains[cwd]


def worktree_main(cwd):
    """Main checkout when cwd is in a linked worktree, else None. Events store it, so they still resolve after the
    worktree is removed."""
    main = git_main(cwd)
    return main if main and not (cwd == main or cwd.startswith(main + '/')) else None


def rule_for(cwd, rules, main=None):
    """Longest rule for cwd. The main checkout's rule takes over when cwd has none, or when cwd's rule also covers the
    main checkout (a catch-all like ~/Repos), so a worktree resolves like its repo unless it has a rule of its own."""
    pre = longest_prefix(cwd, rules)
    if main:
        main_pre = longest_prefix(main, rules)
        if main_pre is not None and (pre is None or main == pre or main.startswith(pre + '/')):
            return main_pre
    return pre


def resolve_cwd(cwd, rules, main=None):
    """What the logger records for an event in `cwd`. `main` is a worktree's stored main checkout; without it, it is
    looked up, which needs cwd to still exist."""
    main = main or worktree_main(cwd)
    pre = rule_for(cwd, rules, main)
    return rules[pre] if pre is not None else resolve(cwd, rules, main or git_top(cwd))


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

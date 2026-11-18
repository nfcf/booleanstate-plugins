#!/usr/bin/env python3
"""Set up cctime for Claude Code running inside a dev container.

  cctime_container.py <repo>     # install the sh logger into <repo>/.cctime/ and register the repo
  cctime_container.py --list     # registered repos and whether their log exists

The container can't see ~/.cctime, so it logs into the bind-mounted repo instead; the report reads
<repo>/.cctime/events.jsonl for every repo in $CCTIME_HOME/repos.json. The logger is hidden from git
through .git/info/exclude, so nothing changes in the client's repo or devcontainer config.
"""
import argparse, glob, json, os, shutil, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cctime_common as c

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = ('log.sh', 'setup-container.sh')


def git_exclude(repo):
    try:
        ex = subprocess.run(['git', '-C', repo, 'rev-parse', '--git-path', 'info/exclude'],
                            capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception as e:
        return f'could not run git: {e}'
    if not ex:
        return 'not a git repository: .cctime/ is not hidden from git'
    ex = ex if os.path.isabs(ex) else os.path.join(repo, ex)
    os.makedirs(os.path.dirname(ex), exist_ok=True)
    cur = open(ex).read() if os.path.exists(ex) else ''
    if '.cctime/' not in cur.split():
        with open(ex, 'a') as f:
            f.write(('' if cur.endswith('\n') or not cur else '\n') + '.cctime/\n')
    return None


def register(repo):
    """Add repo to repos.json. The first time, also adopt repos found by the legacy ~/Repos/* glob,
    so containers set up before repos.json existed keep being counted."""
    adopted = []
    if os.path.exists(c.REPOS):
        with open(c.REPOS) as f:
            data = json.load(f)
    else:
        legacy = glob.glob(c.LEGACY_REPO_LOGS) + glob.glob(os.path.join(os.path.dirname(c.LEGACY_REPO_LOGS), 'log.sh'))
        adopted = sorted({c.tilde(os.path.dirname(os.path.dirname(p))) for p in legacy})   # incl. loggers with no log yet
        data = {'repos': list(adopted)}
    repos = data.setdefault('repos', [])
    if c.tilde(repo) not in repos and repo not in repos:
        repos.append(c.tilde(repo))
    os.makedirs(c.HOME, exist_ok=True)
    tmp = c.REPOS + '.tmp'
    with open(tmp, 'w') as f: json.dump(data, f, indent=2)
    os.replace(tmp, c.REPOS)
    return [r for r in adopted if r != c.tilde(repo)]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('repo', nargs='?')
    ap.add_argument('--list', action='store_true')
    a = ap.parse_args(argv)
    if a.list or not a.repo:
        repos = c.load_repos()
        if not os.path.exists(c.REPOS):
            print('No repos.json yet; the report reads ~/Repos/*/.cctime/events.jsonl.')
        for r in repos:
            log = os.path.join(r, '.cctime', 'events.jsonl')
            print(f'  {c.tilde(r):<50}{"logging" if os.path.exists(log) else "no log yet"}')
        if not a.list: ap.print_usage()
        return

    repo = os.path.abspath(os.path.expanduser(a.repo)).rstrip('/')
    if not os.path.isdir(repo): sys.exit(f'Not a folder: {repo}')
    d = os.path.join(repo, '.cctime'); os.makedirs(d, exist_ok=True)
    for f in FILES:
        shutil.copy(os.path.join(HERE, 'container', f), os.path.join(d, f))
        os.chmod(os.path.join(d, f), 0o755)
    warn = git_exclude(repo)
    adopted = register(repo)
    print(f'Container logger installed in {c.tilde(d)}' + (f' ({warn})' if warn else ' (hidden via .git/info/exclude)'))
    print(f'Registered in {c.tilde(c.REPOS)}')
    if adopted:
        print('Also registered existing container logs: ' + ', '.join(adopted))
    print('\nNow run this once inside the dev container, then restart Claude Code there:')
    print(f'  sh <workspace folder>/.cctime/setup-container.sh      (e.g. sh /workspaces/{os.path.basename(repo)}/.cctime/setup-container.sh)')


if __name__ == '__main__':
    main()

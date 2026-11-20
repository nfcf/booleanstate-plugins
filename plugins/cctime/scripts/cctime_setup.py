#!/usr/bin/env python3
"""Map folders to clients in $CCTIME_HOME/projects.json without hand-editing JSON.

  cctime_setup.py list                         # JSON: unmapped folders (last 90 days), current rules, suggestions
  cctime_setup.py diff  --rules '{"~/Repos/acme": "Acme"}'   # show the change, write nothing
  cctime_setup.py apply --rules '{"~/Repos/acme": "Acme"}'   # back up projects.json, write it, relabel past events
  cctime_setup.py diff | apply                 # no --rules: only relabel past events with the current rules

Rules are folder prefixes; the longest matching prefix wins. The logger stores the project with each event, so
apply also rewrites the stored events (events.jsonl, backfill.jsonl, each backed up first) whose folder a rule
now maps to a different client. Events in folders no rule maps keep the name they were logged with.
"""
import argparse, difflib, json, os, shutil, sys, time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cctime_common as c


def read_raw():
    try:
        with open(c.PROJECTS) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def unmapped_folders(days):
    import cctime_report as r
    from datetime import date, timedelta
    a = r.parser().parse_args([])                            # default sources: events, backfill, repo logs, manual
    d1 = date.today(); d0 = d1 - timedelta(days=days - 1)
    rules = c.load_rules()
    um = r.unmapped(r.collect(a, rules), rules, d0, d1)
    return d0, d1, [{'folder': c.tilde(k), 'git_toplevel': c.tilde(v['git_toplevel']) if v['git_toplevel'] else None,
                     'minutes': round(v['minutes']), 'logged_as': c.resolve(k, rules)}
                    for k, v in sorted(um.items(), key=lambda x: -x[1]['minutes']) if v['minutes'] >= 1]


def suggestions(items):
    """One prefix rule per parent folder that holds two or more unmapped folders."""
    by_parent = defaultdict(list)
    for it in items:
        by_parent[os.path.dirname(it['folder'].rstrip('/'))].append(it['folder'])
    home = c.tilde(os.path.expanduser('~'))
    return [{'prefix': p, 'covers': fs} for p, fs in sorted(by_parent.items())
            if len(fs) > 1 and p not in ('', '/', home)]


def merged(rules):
    new = dict(read_raw())
    for k, v in rules.items():
        key = c.tilde(os.path.expanduser(k).rstrip('/'))
        for old in [o for o in new if os.path.expanduser(o).rstrip('/') == os.path.expanduser(key)]:
            del new[old]                                     # same folder written differently: replace it
        if v in (None, ''):
            continue                                         # empty name removes the rule
        new[key] = v
    return new


def dump(d):
    return json.dumps(d, indent=2, ensure_ascii=False) + '\n'


def backup(path, stamp):
    bak = f'{path}.bak-{stamp}'
    shutil.copy2(path, bak)
    print(f'Backup: {c.tilde(bak)}')


def resolve_stored(cwd, logged, rules, main=None):
    """Project for a stored event under `rules`. A folder that is gone has no git top-level, so its subfolder name
    would stand in for the repo name: use a prefix rule (on the stored main checkout too, for a removed worktree),
    else map the logged name (the repo's basename) by rule."""
    if os.path.isdir(cwd):
        return c.resolve_cwd(cwd, rules, main)
    pre = c.rule_for(cwd, rules, main)
    return rules[pre] if pre is not None else {os.path.basename(k): v for k, v in rules.items()}.get(logged)


def relabel(raw_rules, write, stamp=None):
    """Re-resolve stored events with `raw_rules` ({"~/folder": client}). Returns ({(old, new): count}, number of
    worktree events that get their main checkout recorded). Only events whose folder a rule maps change project.
    With `write`, back up and rewrite each log that changes."""
    rules = {os.path.expanduser(k).rstrip('/'): v for k, v in raw_rules.items()}
    moved, recorded = Counter(), 0
    for path in (c.EVENTS, c.BACKFILL):
        if not os.path.exists(path): continue
        with open(path, 'rb') as f: data = f.read()
        out, n = [], 0
        for line in data.decode('utf-8').splitlines(keepends=True):
            changed = False
            try:
                r = json.loads(line)
                cwd = r.get('cwd')
                if cwd and not r.get('main') and os.path.isdir(cwd):
                    main = c.worktree_main(cwd)                # older worktree events: record their main checkout,
                    if main:                                   # so they keep their client once the worktree is gone
                        r['main'] = main; changed = True; recorded += 1
                new = resolve_stored(cwd, r.get('project'), rules, r.get('main')) if cwd else None
            except Exception:
                new = None
            if new is not None and new != r.get('project') and c.is_mapped(new, rules):
                moved[(r.get('project'), new)] += 1
                r['project'] = new; changed = True
            if changed:
                n += 1
                line = json.dumps(r, ensure_ascii=False) + '\n'
            out.append(line)
        if not (write and n): continue
        backup(path, stamp)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f: f.write(''.join(out))
        with open(path, 'rb') as old:                        # keep events the logger appended while we worked
            old.seek(len(data)); tail = old.read()
            with open(tmp, 'ab') as f: f.write(tail)
            os.replace(tmp, path)
            late = old.read()                                # appended to the old file during the swap
            if late:
                with open(path, 'ab') as f: f.write(late)
    return moved, recorded


def print_moved(result, done):
    moved, recorded = result
    if recorded:
        print(f'{"Recorded" if done else "Would record"} the main checkout on {recorded} worktree events, '
              'so they keep their client after the worktree is removed.')
    if not moved:
        print('No past events to relabel.'); return
    print(f'{"Relabelled" if done else "Would relabel"} {sum(moved.values())} past events:')
    for (old, new), n in sorted(moved.items(), key=lambda x: -x[1]):
        print(f'  {old} -> {new}: {n}')


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['list', 'diff', 'apply'])
    ap.add_argument('--rules', help='JSON object {folder prefix: client name}; an empty name removes a rule')
    ap.add_argument('--days', type=int, default=90)
    a = ap.parse_args(argv)

    if a.cmd == 'list':
        d0, d1, items = unmapped_folders(a.days)
        print(json.dumps({'projects_json': c.tilde(c.PROJECTS), 'from': d0.isoformat(), 'to': d1.isoformat(),
                          'current_rules': read_raw(), 'clients': sorted(set(read_raw().values())),
                          'unmapped': items, 'suggested_parent_rules': suggestions(items)}, indent=2, ensure_ascii=False))
        return

    try:
        rules = json.loads(a.rules or '{}')
        assert isinstance(rules, dict) and all(isinstance(k, str) and isinstance(v, (str, type(None))) for k, v in rules.items())
    except Exception:
        sys.exit('--rules must be a JSON object of {"folder prefix": "client name"}')
    new_rules = merged(rules)
    old_txt = dump(read_raw()) if os.path.exists(c.PROJECTS) else ''
    new_txt = dump(new_rules)
    diff = ''.join(difflib.unified_diff(old_txt.splitlines(True), new_txt.splitlines(True),
                                        'projects.json (current)', 'projects.json (new)'))
    if a.cmd == 'diff':
        print(diff or 'No change to projects.json.')
        print_moved(relabel(new_rules, write=False), done=False); return
    stamp = time.strftime('%Y%m%d-%H%M%S')
    if diff:
        os.makedirs(c.HOME, exist_ok=True)
        if os.path.exists(c.PROJECTS): backup(c.PROJECTS, stamp)
        tmp = c.PROJECTS + '.tmp'
        with open(tmp, 'w') as f: f.write(new_txt)
        os.replace(tmp, c.PROJECTS)                          # before relabelling, so new events already use it
        print(f'Written: {c.tilde(c.PROJECTS)}')
    else:
        print('No change to projects.json.')
    print_moved(relabel(new_rules, write=True, stamp=stamp), done=True)


if __name__ == '__main__':
    main()

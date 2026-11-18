#!/usr/bin/env python3
"""Map folders to clients in $CCTIME_HOME/projects.json without hand-editing JSON.

  cctime_setup.py list                         # JSON: unmapped folders (last 90 days), current rules, suggestions
  cctime_setup.py diff  --rules '{"~/Repos/acme": "Acme"}'   # show the change, write nothing
  cctime_setup.py apply --rules '{"~/Repos/acme": "Acme"}'   # back up projects.json, then write it

Rules are folder prefixes; the longest matching prefix wins. They apply at log time: events logged earlier
keep their old project name unless the report is run with --remap.
"""
import argparse, difflib, json, os, shutil, sys, time
from collections import defaultdict

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

    if not a.rules: sys.exit('--rules is required')
    try:
        rules = json.loads(a.rules)
        assert isinstance(rules, dict) and all(isinstance(k, str) and isinstance(v, (str, type(None))) for k, v in rules.items())
    except Exception:
        sys.exit('--rules must be a JSON object of {"folder prefix": "client name"}')
    old_txt = dump(read_raw()) if os.path.exists(c.PROJECTS) else ''
    new_txt = dump(merged(rules))
    diff = ''.join(difflib.unified_diff(old_txt.splitlines(True), new_txt.splitlines(True),
                                        'projects.json (current)', 'projects.json (new)'))
    if a.cmd == 'diff':
        print(diff or 'No change.'); return
    if not diff:
        print('No change.'); return
    os.makedirs(c.HOME, exist_ok=True)
    if os.path.exists(c.PROJECTS):
        bak = f'{c.PROJECTS}.bak-{time.strftime("%Y%m%d-%H%M%S")}'
        shutil.copy2(c.PROJECTS, bak)
        print(f'Backup: {c.tilde(bak)}')
    tmp = c.PROJECTS + '.tmp'
    with open(tmp, 'w') as f: f.write(new_txt)
    os.replace(tmp, c.PROJECTS)
    print(f'Written: {c.tilde(c.PROJECTS)}')
    print('New rules apply to events logged from now on. Earlier events keep their old project name;\n'
          'run the report with --remap (e.g. "/cctime:report last month remap") to re-resolve them.')


if __name__ == '__main__':
    main()

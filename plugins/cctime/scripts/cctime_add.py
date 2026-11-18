#!/usr/bin/env python3
"""Manual time entries (work outside Claude Code) in $CCTIME_HOME/manual.csv.

  cctime_add.py --project Acme --start 14:00 --end 14:45 --note "sprint review"
  cctime_add.py --project Acme --duration 45m                 # ending now
  cctime_add.py --project Acme --duration 1h30 --end 12:00 --date yesterday
  cctime_add.py --list [N]                                    # last N rows (default 5)
  cctime_add.py --undo                                        # remove the last row
  cctime_add.py --known                                       # client names already in use

Durations: 45m, 1h, 1h30, 1h30m, 1.5h. Entries cannot cross midnight.
A project name that is neither in projects.json nor in manual.csv is refused unless --new-project
(a typo would otherwise become its own report row).
"""
import argparse, csv, os, re, sys
from datetime import date, datetime, timedelta, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cctime_common as c

HEADER = ['date', 'project', 'start', 'end', 'note']


def parse_duration(s):
    """'45m' '1h' '1h30' '1h30m' '1.5h' -> minutes (int). ValueError otherwise."""
    t = s.strip().lower().replace(',', '.').replace(' ', '')
    m = re.fullmatch(r'(\d+(?:\.\d+)?)h(?:(\d+)m?)?', t) or re.fullmatch(r'()(\d+)m(?:in)?', t)
    if not m: raise ValueError(f'not a duration: {s!r} (use 45m, 1h, 1h30, 1.5h)')
    mins = round(float(m.group(1) or 0) * 60) + int(m.group(2) or 0)
    if mins <= 0: raise ValueError('duration must be positive')
    return mins


def parse_date(s, today):
    d = {'today': today, 'hoje': today, 'yesterday': today - timedelta(days=1), 'ontem': today - timedelta(days=1)}.get(s.lower())
    return d or date.fromisoformat(s)


def read_rows(path):
    if not os.path.exists(path): return []
    with open(path, newline='') as f:
        return [r for r in csv.reader(f) if r]                # ignore blank lines


def fmt_row(r):
    d, p, s, e = r[:4]; note = r[4] if len(r) > 4 else ''
    mins = (int(e[:2]) * 60 + int(e[3:5])) - (int(s[:2]) * 60 + int(s[3:5]))
    return f'{d} {p} {s}-{e} ({mins // 60}h{mins % 60:02d}) {note}'.rstrip()


def known_projects(path):
    names = set(c.load_rules().values())
    names.update(r[1] for r in read_rows(path)[1:] if len(r) > 1)
    return sorted(names)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', default='today'); ap.add_argument('--project')
    ap.add_argument('--start'); ap.add_argument('--end'); ap.add_argument('--duration')
    ap.add_argument('--note', default='')
    ap.add_argument('--new-project', action='store_true', help='allow a project name not used before')
    ap.add_argument('--list', nargs='?', const=5, type=int, metavar='N')
    ap.add_argument('--undo', action='store_true')
    ap.add_argument('--known', action='store_true')
    ap.add_argument('--file', default=c.MANUAL)
    a = ap.parse_args(argv)
    path = a.file

    if a.known:
        print('\n'.join(known_projects(path)) or '(none yet)'); return
    if a.list is not None:
        rows = read_rows(path)[1:]
        for r in rows[-a.list:]: print(fmt_row(r))
        if not rows: print('No manual entries yet.')
        return
    if a.undo:
        rows = read_rows(path)
        if len(rows) < 2: sys.exit('No manual entries to undo.')
        last = rows.pop()
        with open(path, 'w', newline='') as f: csv.writer(f).writerows(rows)
        print(f'Removed: {fmt_row(last)}'); return

    if not a.project: sys.exit('--project is required')
    known = known_projects(path)
    if known and a.project not in known and not a.new_project:
        sys.exit(f'Unknown project "{a.project}". Known: {", ".join(known)}\n'
                 'Use one of these, or pass --new-project to create a new one.')
    now = datetime.now().replace(second=0, microsecond=0)
    try:
        d = parse_date(a.date, now.date())
        if a.duration:
            mins = parse_duration(a.duration)
            if a.start and a.end: sys.exit('Give --duration with --start or --end, not both.')
            if a.start:
                s = datetime.combine(d, time.fromisoformat(a.start)); e = s + timedelta(minutes=mins)
            else:
                if not a.end and d != now.date(): sys.exit('For a past date, give --end HH:MM with --duration.')
                e = datetime.combine(d, time.fromisoformat(a.end)) if a.end else now
                s = e - timedelta(minutes=mins)
            if s.date() != d or e.date() != d:
                sys.exit('Entries cannot cross midnight; split it into two.')
            s, e = s.time(), e.time()
        else:
            if not (a.start and a.end): sys.exit('Give --start and --end, or --duration.')
            s, e = time.fromisoformat(a.start), time.fromisoformat(a.end)
    except ValueError as ex:
        sys.exit(f'Invalid date/time: {ex}')
    if e <= s: sys.exit('End must be after start (entries cannot cross midnight).')
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    new = not os.path.exists(path)
    with open(path, 'a', newline='') as f:
        w = csv.writer(f)
        if new: w.writerow(HEADER)
        row = [d.isoformat(), a.project, s.strftime('%H:%M'), e.strftime('%H:%M'), a.note]
        w.writerow(row)
    print(f'Added: {fmt_row(row)}')


if __name__ == '__main__':
    main()

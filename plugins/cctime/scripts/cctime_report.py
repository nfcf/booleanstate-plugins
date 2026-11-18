#!/usr/bin/env python3
"""cctime report: turn $CCTIME_HOME/events.jsonl into time per project.

Per Claude session:
  agent time  = UserPromptSubmit -> Stop/StopFailure/SessionEnd/next prompt (capped by --max-run)
  review time = Stop -> next prompt in the same session, if the gap is <= --idle
Per project, agent + review intervals are merged (two sessions on the same project don't double count).
Across projects they are NOT merged: each project gets its own total.
The report also shows wall-clock time (everything merged) so the overlap is visible.

Usage:
  cctime_report.py                    # this week (Mon..today)
  cctime_report.py --last-week | --today | --yesterday | --this-month | --last-month
  cctime_report.py --from 2026-11-01 --to 2026-11-30 --round 15 --csv nov.csv
  cctime_report.py --remap            # re-resolve projects from each event's folder with today's projects.json
  cctime_report.py --unmapped --json  # folders not mapped to a client (default: last 90 days)
"""
import argparse, csv, glob, json, os, sys
from collections import defaultdict
from datetime import datetime, timedelta, date, time as dtime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cctime_common as c

START, END = {'UserPromptSubmit'}, {'Stop', 'StopFailure', 'SessionEnd'}
SUB_START, SUB_END = 'SubagentStart', 'SubagentStop'


def load(path):
    out = []
    if not os.path.exists(path): return out
    with open(path) as f:
        for line in f:
            try:
                r = json.loads(line); r['t'] = c.parse_ts(r['ts']).astimezone(); out.append(r)
            except Exception:
                pass
    return sorted(out, key=lambda r: r['t'])


def load_repo_logs(files, rules):
    """Dev-container logs: the project comes from the repo folder that holds the log."""
    out = []
    for f in files:
        repo = os.path.dirname(os.path.dirname(f)); proj = c.resolve(repo, rules)
        for r in load(f):
            r['project'] = proj; r['_repo'] = repo
            r['ticket'] = c.ticket_for(r.get('branch'))
            out.append(r)
    return out


def intervals(events, max_run, idle):
    """Return list of (project, start, end, kind, ticket, source_event)."""
    by_session = defaultdict(list)
    for e in events: by_session[e.get('session')].append(e)
    out = []
    for evs in by_session.values():
        run_start = None; last_stop = None
        subs = {}                                               # agent_id -> SubagentStart event (incl. background agents)
        for e in evs:
            ev, t, proj = e.get('event'), e['t'], e.get('project') or 'unknown'
            if ev == SUB_START:
                subs[e.get('agent_id') or f'_{len(subs)}_{t}'] = e
                continue
            if ev == SUB_END:
                k = e.get('agent_id')
                if k not in subs and subs: k = next(iter(subs))  # no id on stop: close the oldest open one
                s = subs.pop(k, None)
                if s is not None:
                    out.append((s.get('project') or proj, s['t'], min(t, s['t'] + max_run), 'agent', s.get('ticket'),
                                s if s.get('project') else e))
                continue
            if ev == 'SessionEnd':                              # session closed: close any agent still open
                for s in subs.values():
                    out.append((s.get('project') or proj, s['t'], min(t, s['t'] + max_run), 'agent', s.get('ticket'),
                                s if s.get('project') else e))
                subs = {}
            if ev in START:
                if run_start is not None:                       # previous run never got a Stop (e.g. interrupted)
                    out.append((proj, run_start, min(t, run_start + max_run), 'agent', e.get('ticket'), e))
                if last_stop is not None and t - last_stop <= idle:
                    out.append((proj, last_stop, t, 'review', e.get('ticket'), e))
                run_start, last_stop = t, None
            elif ev in END and run_start is not None:
                out.append((proj, run_start, min(t, run_start + max_run), 'agent', e.get('ticket'), e))
                run_start, last_stop = None, (t if ev != 'SessionEnd' else None)
            elif ev == 'SessionEnd':
                last_stop = None
    return out


def merge(spans):
    spans = sorted(spans); out = []
    for s, e in spans:
        if out and s <= out[-1][1]: out[-1][1] = max(out[-1][1], e)
        else: out.append([s, e])
    return out


def split_by_day(s, e):
    while s.date() < e.date():
        nxt = datetime.combine(s.date() + timedelta(days=1), dtime.min, s.tzinfo)
        yield s, nxt; s = nxt
    if e > s: yield s, e


def minutes(spans): return sum((e - s).total_seconds() for s, e in spans) / 60


def fmt(m, rnd):
    if rnd: m = (int(m + rnd - 1) // rnd) * rnd if m > 0 else 0
    return f'{int(m // 60)}h{int(m % 60):02d}', m


def folder_of(e, rules):
    """(folder, git top-level, mapped?) for the event an interval was attributed to. None for manual rows."""
    if e is None: return None
    if e.get('_repo'):                                          # dev-container log: the repo on this machine
        return e['_repo'], e['_repo'], c.is_mapped(c.resolve(e['_repo'], rules), rules)
    cwd = e.get('cwd')
    if not cwd: return None
    top = c.git_top(cwd)
    return top or cwd, top or None, c.is_mapped(c.resolve_cwd(cwd, rules), rules)


def unmapped(iv, rules, d0, d1):
    """{folder: {'minutes', 'git_toplevel'}} for time in [d0, d1] whose folder no projects.json rule maps."""
    spans = defaultdict(list); tops = {}; info = {}
    for proj, s, e, kind, tk, src in iv:
        key = id(src)
        if key not in info: info[key] = folder_of(src, rules)
        f = info[key]
        if f is None or f[2]: continue
        for ds, de in split_by_day(s, e):
            if d0 <= ds.date() <= d1:
                spans[f[0]].append((ds, de)); tops[f[0]] = f[1]
    return {k: {'minutes': minutes(merge(v)), 'git_toplevel': tops[k]} for k, v in spans.items()}


def collect(a, rules):
    files = glob.glob(os.path.expanduser(a.repo_logs)) if a.repo_logs else c.repo_log_files()
    evs = sorted(load(a.events) + load(a.backfill) + load_repo_logs(files, rules), key=lambda r: r['t'])
    if a.remap:
        for r in evs:
            if r.get('_repo'): continue                         # container logs already resolve from the repo folder
            if r.get('cwd'): r['project'] = c.resolve_cwd(r['cwd'], rules)
    iv = intervals(evs, timedelta(minutes=a.max_run), timedelta(minutes=a.idle))
    tz = datetime.now().astimezone().tzinfo
    if os.path.exists(a.manual):
        with open(a.manual) as f:
            for row in csv.DictReader(f):
                d = date.fromisoformat(row['date'])
                s = datetime.combine(d, dtime.fromisoformat(row['start']), tz); e = datetime.combine(d, dtime.fromisoformat(row['end']), tz)
                iv.append((row['project'], s, e, 'manual', None, None))
    return iv


def period(a, today):
    monday = today - timedelta(days=today.weekday())
    if a.last_week: d0, d1 = monday - timedelta(days=7), monday - timedelta(days=1)
    elif a.today: d0 = d1 = today
    elif a.yesterday: d0 = d1 = today - timedelta(days=1)
    elif a.this_month: d0, d1 = today.replace(day=1), today
    elif a.last_month:
        d1 = today.replace(day=1) - timedelta(days=1); d0 = d1.replace(day=1)
    elif a.unmapped: d0, d1 = today - timedelta(days=89), today
    else: d0, d1 = monday, today
    if a.frm: d0 = date.fromisoformat(a.frm)
    if a.to: d1 = date.fromisoformat(a.to)
    return d0, d1


def parser():
    ap = argparse.ArgumentParser()
    ap.add_argument('--from', dest='frm'); ap.add_argument('--to')
    ap.add_argument('--last-week', action='store_true')
    ap.add_argument('--today', action='store_true')
    ap.add_argument('--yesterday', action='store_true')
    ap.add_argument('--this-month', action='store_true')
    ap.add_argument('--last-month', action='store_true')
    ap.add_argument('--idle', type=int, default=10, help='max minutes between Stop and next prompt to count as review')
    ap.add_argument('--max-run', type=int, default=90, help='cap for a single agent run, minutes')
    ap.add_argument('--round', type=int, default=0, help='round each project/day up to N minutes (e.g. 15)')
    ap.add_argument('--manual', default=c.MANUAL)
    ap.add_argument('--events', default=c.EVENTS)
    ap.add_argument('--backfill', default=c.BACKFILL, help='events synthesized by cctime_backfill.py')
    ap.add_argument('--repo-logs', help='glob of dev-container logs (default: repos in repos.json, '
                                        'or ~/Repos/*/.cctime/events.jsonl when repos.json does not exist)')
    ap.add_argument('--remap', action='store_true', help="re-resolve every event's project with the current projects.json")
    ap.add_argument('--unmapped', action='store_true', help='only list folders not mapped to a client (default: last 90 days)')
    ap.add_argument('--json', action='store_true', help='with --unmapped: print JSON')
    ap.add_argument('--plain', action='store_true', help='the original plain layout (stable, for scripts)')
    ap.add_argument('--csv')
    return ap


def main():
    a = parser().parse_args()
    d0, d1 = period(a, date.today())
    rules = c.load_rules()
    iv = collect(a, rules)

    if a.unmapped:
        um = unmapped(iv, rules, d0, d1)
        items = [{'folder': c.tilde(k), 'git_toplevel': c.tilde(v['git_toplevel']) if v['git_toplevel'] else None,
                  'minutes': round(v['minutes']), 'logged_as': c.resolve(k, rules)}
                 for k, v in sorted(um.items(), key=lambda x: -x[1]['minutes'])]
        if a.json:
            print(json.dumps({'from': d0.isoformat(), 'to': d1.isoformat(), 'unmapped': items}, indent=2, ensure_ascii=False))
        else:
            print(f'Unmapped folders {d0} .. {d1}:')
            for it in items: print(f'  {it["folder"]:<50}{fmt(it["minutes"],0)[0]:>8}')
            if not items: print('  none')
        return

    per = defaultdict(list); kinds = defaultdict(lambda: defaultdict(list)); tickets = defaultdict(set); allspans = defaultdict(list)
    for proj, s, e, kind, tk, _src in iv:
        for ds, de in split_by_day(s, e):
            if not (d0 <= ds.date() <= d1): continue
            per[(ds.date(), proj)].append((ds, de)); kinds[(ds.date(), proj)][kind].append((ds, de))
            allspans[ds.date()].append((ds, de))
            if tk: tickets[(ds.date(), proj)].add(tk)

    if a.plain:
        print(f'cctime {d0} .. {d1}   (idle {a.idle} min, max run {a.max_run} min' + (f', rounding {a.round} min' if a.round else '') + ')\n')
    else:
        span = day_label(d0, True) if d0 == d1 else f'{day_label(d0, d0.year != d1.year)} – {day_label(d1, True)}'
        print(f'cctime · {span}')
        print(f'idle {a.idle} min · max run {a.max_run} min' + (f' · rounded up to {a.round} min (wall clock unrounded)' if a.round else '') + '\n')
    if not per:
        print('No activity logged in this period.')
        return

    # one entry per day: [(project, billed, agent, review, manual, tickets)], wall clock
    days = []; rows = []
    for day in sorted({d for d, _ in per}):
        entries = []
        for (d, proj) in sorted(k for k in per if k[0] == day):
            k = kinds[(d, proj)]
            billed = fmt(minutes(merge(per[(d, proj)])), a.round)[1]
            ag, rv, mn = (minutes(merge(k[x])) for x in ('agent', 'review', 'manual'))
            tks = ' '.join(sorted(tickets[(d, proj)]))
            entries.append((proj, billed, ag, rv, mn, tks, minutes(merge(per[(d, proj)]))))
            rows.append([d.isoformat(), proj, round(billed / 60, 2), round(ag / 60, 2), round(rv / 60, 2), round(mn / 60, 2), tks])
        days.append((day, entries, minutes(merge(allspans[day]))))
    um = sorted(((k, v['minutes']) for k, v in unmapped(iv, rules, d0, d1).items() if v['minutes'] >= 1), key=lambda x: -x[1])
    (print_plain if a.plain else print_pretty)(a, d0, d1, days, um)
    if a.csv:
        with open(a.csv, 'w', newline='') as f:
            w = csv.writer(f); w.writerow(['date', 'project', 'active_h', 'agent_h', 'review_h', 'manual_h', 'tickets']); w.writerows(rows)
        print(f'\nCSV written: {a.csv}')


def totals(days):
    tot_proj = defaultdict(float)
    for _, entries, _ in days:
        for e in entries: tot_proj[e[0]] += e[1]
    billed = sum(tot_proj.values()); wall = sum(w for _, _, w in days)
    return sorted(tot_proj.items(), key=lambda x: -x[1]), billed, wall


def hm(m): return fmt(m, 0)[0]


def print_plain(a, d0, d1, days, um):
    """The original cctime layout, kept for scripts that read the output."""
    print(f'{"date":<11}{"project":<22}{"active":>8}{"agent":>8}{"review":>8}{"manual":>8}  tickets')
    for day, entries, wall in days:
        for proj, billed, ag, rv, mn, tks, _raw in entries:
            print(f'{day.isoformat():<11}{proj[:21]:<22}{fmt(billed, a.round)[0]:>8}{hm(ag):>8}{hm(rv):>8}{hm(mn):>8}  {tks}')
        print(f'{"":<11}{"(wall clock)":<22}{hm(wall):>8}\n')
    tot, billed, wall = totals(days)
    print('TOTAL per project:')
    for p, m in tot: print(f'  {p:<30}{hm(m):>8}')
    print(f'  {"sum of projects":<30}{hm(billed):>8}')
    print(f'  {"wall clock (no double count)":<30}{hm(wall):>8}')
    print(f'  {"parallel overlap":<30}{hm(max(0, billed - wall)):>8}')
    if um:
        print('\nUnmapped folders (no projects.json rule; run /cctime:setup to assign them):')
        for k, m in um: print(f'  {c.tilde(k):<50}{hm(m):>8}')


WEEKDAYS = 'Mon Tue Wed Thu Fri Sat Sun'.split()
MONTHS = 'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split()


def day_label(d, year=False):
    return f'{WEEKDAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}' + (f' {d.year}' if year else '')


def clip(s, n): return s if len(s) <= n else s[:n - 1] + '…'


def print_pretty(a, d0, d1, days, um):
    tot, billed, wall = totals(days)
    tot = [(p, m) for p, m in tot if m >= 1]                     # clients under a minute are left out (still in the sums)
    w = min(28, max([16] + [len(p) for p, _ in tot]))          # project column width (fits 'parallel overlap')
    raw = sum(e[6] for _, entries, _ in days for e in entries)   # unrounded, so rounding is not counted as overlap
    cell = lambda m: f'{hm(m) if m >= 1 else "·":>7}'           # '·' instead of 0h00
    rule = '  ' + '─' * (w + 32)
    for day, entries, day_wall in days:
        entries = [e for e in entries if e[1] >= 1]
        if not entries: continue
        print(f'{day_label(day, d0.year != d1.year):<{w + 2}}{"active":>7}{"agent":>8}{"review":>8}{"manual":>8}')
        for proj, b, ag, rv, mn, tks, _raw in entries:
            print(f'  {clip(proj, w):<{w}}{fmt(b, a.round)[0]:>7} {cell(ag)} {cell(rv)} {cell(mn)}' + (f'   {tks}' if tks else ''))
        if len(entries) > 1:
            print(f'  {"wall clock":<{w}}{hm(day_wall):>7}')
        print()
    print(rule)
    print(f'  {"TOTAL":<{w}}{"active":>7}')
    top = max((m for _, m in tot), default=0) or 1
    for p, m in tot:
        bar = '█' * max(1, round(20 * m / top))
        pct = round(100 * m / billed) if billed else None
        pct = '' if pct is None else ' <1%' if pct == 0 else f'{pct:>3}%'
        print(f'  {clip(p, w):<{w}}{hm(m):>7}  {bar:<20}  {pct}')
    print(rule)
    print(f'  {"sum of projects":<{w}}{hm(billed):>7}')
    print(f'  {"wall clock":<{w}}{hm(wall):>7}  no double count')
    print(f'  {"parallel overlap":<{w}}{hm(max(0, raw - wall)):>7}  different projects at the same time')
    if um:
        print('\nUnmapped folders (no projects.json rule; run /cctime:setup to assign them):')
        for k, m in um: print(f'  {clip(c.tilde(k), w + 20):<{w + 20}}{hm(m):>7}')

if __name__ == '__main__':
    main()

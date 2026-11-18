import csv, json, os
from helpers import Sandbox, ev, rows, total

D, D2 = '2026-01-05', '2026-01-06'
PERIOD = ('--from', D, '--to', D2)


class ReportTest(Sandbox):
    def test_prompt_stop_prompt_within_idle(self):
        self.write_events([ev(D, '10:00', 'UserPromptSubmit'), ev(D, '10:20', 'Stop'),
                           ev(D, '10:25', 'UserPromptSubmit'), ev(D, '10:30', 'Stop')])
        self.assertEqual(rows(self.report(*PERIOD))[(D, 'Acme')][:3], ['0h30', '0h25', '0h05'])

    def test_gap_over_idle_has_no_review(self):
        self.write_events([ev(D, '10:00', 'UserPromptSubmit'), ev(D, '10:20', 'Stop'),
                           ev(D, '10:45', 'UserPromptSubmit'), ev(D, '10:50', 'Stop')])
        self.assertEqual(rows(self.report(*PERIOD))[(D, 'Acme')][:3], ['0h25', '0h25', '0h00'])

    def test_run_over_max_run_is_capped(self):
        self.write_events([ev(D, '10:00', 'UserPromptSubmit'), ev(D, '12:30', 'Stop')])
        self.assertEqual(rows(self.report(*PERIOD))[(D, 'Acme')][:2], ['1h30', '1h30'])
        self.assertEqual(rows(self.report(*PERIOD, '--max-run', '120'))[(D, 'Acme')][0], '2h00')

    def test_parallel_sessions_same_project_merge(self):
        self.write_events([ev(D, '10:00', 'UserPromptSubmit', 's1'), ev(D, '10:30', 'UserPromptSubmit', 's2'),
                           ev(D, '11:00', 'Stop', 's1'), ev(D, '11:30', 'Stop', 's2')])
        out = self.report(*PERIOD)
        self.assertEqual(rows(out)[(D, 'Acme')][0], '1h30')
        self.assertEqual(total(out, 'parallel overlap'), '0h00')

    def test_parallel_sessions_different_projects_both_count(self):
        self.write_events([ev(D, '10:00', 'UserPromptSubmit', 's1', 'Acme'), ev(D, '10:30', 'UserPromptSubmit', 's2', 'ClientB'),
                           ev(D, '11:00', 'Stop', 's1', 'Acme'), ev(D, '11:30', 'Stop', 's2', 'ClientB')])
        out = self.report(*PERIOD)
        r = rows(out)
        self.assertEqual(r[(D, 'Acme')][0], '1h00'); self.assertEqual(r[(D, 'ClientB')][0], '1h00')
        self.assertEqual(total(out, 'sum of projects'), '2h00')
        self.assertEqual(total(out, 'wall clock (no double count)'), '1h30')
        self.assertEqual(total(out, 'parallel overlap'), '0h30')

    def test_subagent_counts_as_agent(self):
        self.write_events([ev(D, '10:00', 'SubagentStart', agent_id='a1'), ev(D, '10:40', 'SubagentStop', agent_id='a1')])
        self.assertEqual(rows(self.report(*PERIOD))[(D, 'Acme')][:2], ['0h40', '0h40'])

    def test_run_crossing_midnight_splits_by_day(self):
        self.write_events([ev(D, '23:30', 'UserPromptSubmit'), ev(D2, '00:20', 'Stop')])
        r = rows(self.report(*PERIOD))
        self.assertEqual(r[(D, 'Acme')][0], '0h30'); self.assertEqual(r[(D2, 'Acme')][0], '0h20')

    def test_manual_row_overlapping_agent_counted_once(self):
        self.write_events([ev(D, '10:00', 'UserPromptSubmit'), ev(D, '11:00', 'Stop')])
        with open(os.path.join(self.home, 'manual.csv'), 'w') as f:
            f.write(f'date,project,start,end,note\n{D},Acme,10:30,11:30,call\n')
        self.assertEqual(rows(self.report(*PERIOD))[(D, 'Acme')][:4], ['1h30', '1h00', '0h00', '1h00'])

    def test_round_15(self):
        self.write_events([ev(D, '10:00', 'UserPromptSubmit'), ev(D, '10:07', 'Stop')])
        out = self.report(*PERIOD, '--round', '15')
        self.assertEqual(rows(out)[(D, 'Acme')][:2], ['0h15', '0h07'])
        self.assertIn('rounding 15 min', out)

    def test_csv_columns(self):
        self.write_events([ev(D, '10:00', 'UserPromptSubmit', ticket='ABC-1'), ev(D, '10:30', 'Stop', ticket='ABC-1')])
        path = os.path.join(self.tmp, 'out.csv')
        self.report(*PERIOD, '--csv', path)
        with open(path) as f:
            data = list(csv.reader(f))
        self.assertEqual(data[0], ['date', 'project', 'active_h', 'agent_h', 'review_h', 'manual_h', 'tickets'])
        self.assertEqual(data[1], [D, 'Acme', '0.5', '0.5', '0.0', '0.0', 'ABC-1'])

    def test_pretty_layout(self):
        self.write_events([ev(D, '10:00', 'UserPromptSubmit', 's1', 'Acme', ticket='ABC-1'), ev(D, '11:00', 'Stop', 's1', 'Acme', ticket='ABC-1'),
                           ev(D, '10:30', 'UserPromptSubmit', 's2', 'ClientB'), ev(D, '11:00', 'Stop', 's2', 'ClientB')])
        out = self.report('--from', D, '--to', D, pretty=True)
        lines = out.splitlines()
        self.assertEqual(lines[0], 'cctime · Mon 5 Jan 2026')
        self.assertIn('Mon 5 Jan', out)
        self.assertRegex(out, r'\n  Acme +1h00 +1h00 +· +· +ABC-1\n')
        self.assertRegex(out, r'\n  wall clock +1h00\n')                      # two projects that day
        self.assertRegex(out, r'\n  Acme +1h00  █{20} +67%\n')
        self.assertRegex(out, r'\n  parallel overlap +0h30  ')
        self.assertNotIn('0h00', out)

    def test_pretty_rounding_is_not_overlap_and_columns_align(self):
        self.write_events([ev(D, '10:00', 'UserPromptSubmit'), ev(D, '10:07', 'Stop')])
        out = self.report(*PERIOD, '--round', '15', pretty=True)
        self.assertRegex(out, r'\n  parallel overlap +·?0h00  ')
        ends = [l.index('h', 18) for l in out.splitlines() if l.startswith(('  sum of projects', '  wall clock ', '  parallel overlap'))]
        self.assertEqual(len(set(ends)), 1, out)

    def test_pretty_hides_clients_under_a_minute(self):
        self.write_events([ev(D, f'{h:02d}:00', e, f'a{h}', 'Acme') for h in (6, 8, 10) for e in ('UserPromptSubmit',)] +
                          [ev(D, f'{h + 1:02d}:30', 'Stop', f'a{h}', 'Acme') for h in (6, 8, 10)] +   # 270 min
                          [ev(D, '13:00', 'UserPromptSubmit', 's2', 'Tiny'), ev(D, '13:00', 'Stop', 's2', 'Tiny', ts=f'{D}T13:00:20+00:00'),
                           ev(D, '14:00', 'UserPromptSubmit', 's3', 'Small'), ev(D, '14:01', 'Stop', 's3', 'Small'),
                           ev(D2, '09:00', 'UserPromptSubmit', 's4', 'Tiny'), ev(D2, '09:00', 'Stop', 's4', 'Tiny', ts=f'{D2}T09:00:20+00:00')])
        out = self.report(*PERIOD, pretty=True)
        self.assertNotIn('Tiny', out)
        self.assertNotIn('\nTue 6 Jan', out)                                  # a day with only hidden clients
        self.assertRegex(out, r'\n  Small +0h01  █ +<1%\n')
        self.assertIn('Tiny', self.report(*PERIOD))                           # --plain keeps every row

    def test_pretty_headings_show_year_across_years(self):
        self.write_events([ev('2025-12-31', '10:00', 'UserPromptSubmit'), ev('2025-12-31', '10:30', 'Stop'),
                           ev('2026-01-01', '10:00', 'UserPromptSubmit', 's2'), ev('2026-01-01', '10:30', 'Stop', 's2')])
        out = self.report('--from', '2025-12-30', '--to', '2026-01-02', pretty=True)
        self.assertIn('\nWed 31 Dec 2025', out); self.assertIn('\nThu 1 Jan 2026', out)

    def test_empty_period(self):
        self.assertIn('No activity logged in this period.', self.report(*PERIOD))


class UnmappedRemapTest(Sandbox):
    def setUp(self):
        super().setUp()
        self.acme = os.path.join(self.tmp, 'work', 'acme')
        self.other = os.path.join(self.tmp, 'work', 'other')
        self.write_json('projects.json', {'~/work/acme': 'Acme'})

    def test_unmapped_block_lists_folder(self):
        self.write_events([ev(D, '10:00', 'UserPromptSubmit', 's1', 'Acme', self.acme + '/sub'), ev(D, '10:30', 'Stop', 's1', 'Acme', self.acme + '/sub'),
                           ev(D, '11:00', 'UserPromptSubmit', 's2', 'other', self.other), ev(D, '11:45', 'Stop', 's2', 'other', self.other)])
        out = self.report(*PERIOD)
        block = out[out.index('Unmapped folders'):]
        self.assertIn('/cctime:setup', block)
        self.assertIn('~/work/other', block); self.assertIn('0h45', block)
        self.assertNotIn('acme', block)

    def test_no_unmapped_block_when_all_mapped(self):
        self.write_events([ev(D, '10:00', 'UserPromptSubmit', 's1', 'Acme', self.acme), ev(D, '10:30', 'Stop', 's1', 'Acme', self.acme)])
        self.assertNotIn('Unmapped', self.report(*PERIOD))

    def test_unmapped_json(self):
        self.write_events([ev(D, '11:00', 'UserPromptSubmit', 's2', 'other', self.other), ev(D, '11:45', 'Stop', 's2', 'other', self.other)])
        data = json.loads(self.report('--unmapped', '--json', *PERIOD))
        self.assertEqual(data['unmapped'], [{'folder': '~/work/other', 'git_toplevel': None, 'minutes': 45, 'logged_as': 'other'}])

    def test_remap_reresolves_projects(self):
        self.write_events([ev(D, '10:00', 'UserPromptSubmit', 's1', 'old-name', self.acme), ev(D, '10:30', 'Stop', 's1', 'old-name', self.acme)])
        self.assertIn((D, 'old-name'), rows(self.report(*PERIOD)))
        self.assertEqual(list(rows(self.report(*PERIOD, '--remap'))), [(D, 'Acme')])

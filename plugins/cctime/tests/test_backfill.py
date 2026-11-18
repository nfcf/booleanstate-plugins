import json, os
from helpers import Sandbox, ev, rows, read

D = '2026-01-05'


def line(kind, hm, session, content=None, **extra):
    r = {'type': kind, 'timestamp': f'{D}T{hm}:00.123Z', 'sessionId': session, 'cwd': '/nonexistent/acme',
         'gitBranch': 'feature/ABC-12-x', 'uuid': f'{session}-{kind}-{hm}-{extra.get("isSidechain", False)}'}
    if kind == 'user':
        r['message'] = {'role': 'user', 'content': content if content is not None else 'do the thing'}
        r.setdefault('origin', {'kind': 'human'})
    else:
        r['message'] = {'role': 'assistant', 'content': [{'type': 'text', 'text': 'ok'}]}
    r.update(extra)
    return r


class BackfillTest(Sandbox):
    def setUp(self):
        super().setUp()
        self.proj = os.path.join(self.tmp, '.claude', 'projects', '-nonexistent-acme')
        os.makedirs(self.proj)
        self.out = os.path.join(self.home, 'backfill.jsonl')

    def transcript(self, session, lines):
        with open(os.path.join(self.proj, session + '.jsonl'), 'w') as f:
            for l in lines: f.write(json.dumps(l) + '\n')

    def events(self):
        return [json.loads(l) for l in read(self.out).splitlines()]

    def test_real_prompts_tool_results_meta_and_sidechain(self):
        tool_result = [{'type': 'tool_result', 'tool_use_id': 'x', 'content': 'out'}]
        self.transcript('s1', [
            line('user', '10:00', 's1'),
            line('assistant', '10:05', 's1'),
            line('user', '10:06', 's1', tool_result, toolUseResult={'stdout': ''}),
            line('assistant', '10:20', 's1'),
            line('user', '10:21', 's1', 'reminder', isMeta=True),
            line('user', '10:22', 's1', '<task-notification>done</task-notification>', origin={'kind': 'task-notification'}),
            line('assistant', '10:50', 's1', isSidechain=True),
            line('user', '10:25', 's1', [{'type': 'text', 'text': 'next'}]),
            line('assistant', '10:30', 's1'),
        ])
        self.run_script('cctime_backfill.py')
        got = [(e['event'], e['ts'][11:16]) for e in self.events()]
        self.assertEqual(got, [('UserPromptSubmit', '10:00'), ('Stop', '10:20'), ('UserPromptSubmit', '10:25'), ('Stop', '10:30')])
        e = self.events()[0]
        self.assertEqual((e['source'], e['project'], e['ticket'], e['session']), ('backfill', 'acme', 'ABC-12', 's1'))
        self.assertNotIn('do the thing', read(self.out))
        # the report reads backfill.jsonl: 20 min agent + 5 min review + 5 min agent
        self.assertEqual(rows(self.report('--from', D, '--to', D))[(D, 'acme')][:3], ['0h30', '0h25', '0h05'])

    def test_dedupe_against_hook_sessions_and_cutoff(self):
        self.transcript('hooked', [line('user', '09:00', 'hooked'), line('assistant', '09:10', 'hooked')])
        self.transcript('old', [line('user', '08:00', 'old'), line('assistant', '08:10', 'old'),
                                line('user', '13:00', 'old'), line('assistant', '13:10', 'old')])
        self.write_events([ev(D, '12:00', 'UserPromptSubmit', 'hooked'), ev(D, '12:30', 'Stop', 'hooked')])
        out = self.run_script('cctime_backfill.py').stdout
        self.assertIn('Skipped 1 sessions', out)
        got = [(e['session'], e['ts'][11:16]) for e in self.events()]
        self.assertEqual(got, [('old', '08:00'), ('old', '08:10')])   # nothing at/after the first hook event

    def test_rerun_is_idempotent_and_dry_run_writes_nothing(self):
        self.transcript('s1', [line('user', '10:00', 's1'), line('assistant', '10:05', 's1')])
        dry = self.run_script('cctime_backfill.py', '--dry-run').stdout
        self.assertIn('Dry run', dry); self.assertFalse(os.path.exists(self.out))
        self.run_script('cctime_backfill.py'); first = read(self.out)
        self.run_script('cctime_backfill.py'); self.assertEqual(read(self.out), first)
        self.assertEqual(len(first.splitlines()), 2)

    def test_unanswered_prompt_adds_no_agent_time(self):
        self.transcript('s1', [line('user', '10:00', 's1', '<command-name>/clear</command-name>'),
                               line('user', '11:00', 's1'), line('assistant', '11:10', 's1'),
                               line('user', '11:12', 's1', '<command-name>/model</command-name>')])
        self.run_script('cctime_backfill.py')
        got = [(e['event'], e['ts'][11:16]) for e in self.events()]
        self.assertEqual(got, [('UserPromptSubmit', '10:00'), ('Stop', '10:00'), ('UserPromptSubmit', '11:00'),
                               ('Stop', '11:10'), ('UserPromptSubmit', '11:12'), ('Stop', '11:12')])
        self.assertEqual(rows(self.report('--from', D, '--to', D))[(D, 'acme')][:3], ['0h12', '0h10', '0h02'])

    def test_since(self):
        self.transcript('s1', [line('user', '10:00', 's1'), line('assistant', '10:05', 's1')])
        self.run_script('cctime_backfill.py', '--since', '2026-01-06')
        self.assertEqual(self.events(), [])

import json, os, subprocess
from helpers import Sandbox, ev, rows, read, read_json

D = '2026-01-05'


class AddTest(Sandbox):
    def add(self, *args, ok=True):
        return self.run_script('cctime_add.py', *args, ok=ok)

    def manual(self):
        with open(os.path.join(self.home, 'manual.csv')) as f:
            return f.read().splitlines()

    def test_duration_forms(self):
        for dur, start in (('45m', '11:15'), ('1h', '11:00'), ('1h30', '10:30'), ('1.5h', '10:30'), ('1h30m', '10:30')):
            out = self.add('--date', D, '--project', 'Acme', '--duration', dur, '--end', '12:00', '--new-project').stdout
            self.assertIn(f'{start}-12:00', out)
        self.add('--date', D, '--project', 'Acme', '--duration', '2h', '--start', '09:00')
        self.assertEqual(self.manual()[-1], f'{D},Acme,09:00,11:00,')

    def test_duration_ending_now(self):
        out = self.add('--project', 'Acme', '--duration', '1m').stdout
        self.assertIn('(0h01)', out)

    def test_range_still_works_and_undo_list(self):
        self.add('--date', D, '--project', 'Acme', '--start', '14:00', '--end', '14:45', '--note', 'sprint review')
        self.add('--date', D, '--project', 'Acme', '--start', '15:00', '--end', '15:30')
        self.assertIn('14:00-14:45 (0h45) sprint review', self.add('--list').stdout)
        self.assertEqual(self.add('--undo').stdout.strip(), f'Removed: {D} Acme 15:00-15:30 (0h30)')
        self.assertEqual(self.manual(), ['date,project,start,end,note', f'{D},Acme,14:00,14:45,sprint review'])
        self.add('--undo')
        self.assertNotEqual(self.add('--undo', ok=False).returncode, 0)

    def test_undo_with_trailing_blank_line(self):
        with open(os.path.join(self.home, 'manual.csv'), 'w') as f:
            f.write(f'date,project,start,end,note\n{D},Acme,10:00,11:00,x\n\n')
        self.assertEqual(self.add('--undo').stdout.strip(), f'Removed: {D} Acme 10:00-11:00 (1h00) x')
        self.assertEqual(self.manual(), ['date,project,start,end,note'])

    def test_midnight_rejected(self):
        self.assertIn('midnight', self.add('--date', D, '--project', 'Acme', '--duration', '1h', '--end', '00:30', ok=False).stderr)
        self.assertIn('midnight', self.add('--date', D, '--project', 'Acme', '--start', '23:00', '--end', '01:00', ok=False).stderr)
        self.assertIn('not a duration', self.add('--date', D, '--project', 'Acme', '--duration', '45', '--end', '12:00', ok=False).stderr)

    def test_unknown_project_refused(self):
        self.write_json('projects.json', {'~/work/acme': 'Acme'})
        p = self.add('--date', D, '--project', 'Acmee', '--start', '10:00', '--end', '11:00', ok=False)
        self.assertIn('Known: Acme', p.stderr)
        self.add('--date', D, '--project', 'Acmee', '--start', '10:00', '--end', '11:00', '--new-project')
        self.assertEqual(self.add('--known').stdout.split(), ['Acme', 'Acmee'])


class SetupTest(Sandbox):
    def test_list_diff_apply_with_backup(self):
        self.write_json('projects.json', {'~/work/acme': 'Acme'})
        for name in ('x', 'y'):
            cwd = os.path.join(self.tmp, 'work', 'clientb', name)
            from datetime import date
            today = date.today().isoformat()
            self.write_events([ev(today, '00:01', 'UserPromptSubmit', name, name, cwd), ev(today, '00:31', 'Stop', name, name, cwd)])
        data = json.loads(self.run_script('cctime_setup.py', 'list').stdout)
        self.assertEqual({u['folder'] for u in data['unmapped']}, {'~/work/clientb/x', '~/work/clientb/y'})
        self.assertEqual(data['suggested_parent_rules'][0]['prefix'], '~/work/clientb')
        rules = json.dumps({'~/work/clientb': 'Client B'})
        diff = self.run_script('cctime_setup.py', 'diff', '--rules', rules).stdout
        self.assertIn('+  "~/work/clientb": "Client B"', diff)
        self.assertEqual(read_json(os.path.join(self.home, 'projects.json')), {'~/work/acme': 'Acme'})
        self.run_script('cctime_setup.py', 'apply', '--rules', rules)
        self.assertEqual(read_json(os.path.join(self.home, 'projects.json')), {'~/work/acme': 'Acme', '~/work/clientb': 'Client B'})
        self.assertEqual(len([f for f in os.listdir(self.home) if f.startswith('projects.json.bak-')]), 1)
        self.assertEqual(json.loads(self.run_script('cctime_setup.py', 'list').stdout)['unmapped'], [])


class ContainerTest(Sandbox):
    def test_install_registers_and_report_reads_it(self):
        os.makedirs(os.path.join(self.tmp, 'Repos', 'quiet', '.cctime'))      # set up earlier, nothing logged yet
        open(os.path.join(self.tmp, 'Repos', 'quiet', '.cctime', 'log.sh'), 'w').close()
        legacy = os.path.join(self.tmp, 'Repos', 'old')
        self.write_events([ev(D, '08:00', 'UserPromptSubmit', 'c0'), ev(D, '08:30', 'Stop', 'c0')],
                          os.path.join(legacy, '.cctime', 'events.jsonl'))
        repo = os.path.join(self.tmp, 'code', 'acme')
        os.makedirs(repo)
        subprocess.run(['git', 'init', '-q', repo], check=True)
        self.write_json('projects.json', {'~/code/acme': 'Acme'})
        out = self.run_script('cctime_container.py', repo).stdout
        self.assertIn('setup-container.sh', out)
        for f in ('log.sh', 'setup-container.sh'):
            self.assertTrue(os.access(os.path.join(repo, '.cctime', f), os.X_OK))
        self.assertIn('.cctime/', read(os.path.join(repo, '.git', 'info', 'exclude')).split())
        self.assertEqual(read_json(os.path.join(self.home, 'repos.json')), {'repos': ['~/Repos/old', '~/Repos/quiet', '~/code/acme']})
        # the container logger itself (sh) writes next to itself; the report attributes it to the repo's client
        for evname, sid in (('UserPromptSubmit', 'c1'), ('Stop', 'c1')):
            subprocess.run(['sh', os.path.join(repo, '.cctime', 'log.sh')], input=json.dumps({'hook_event_name': evname, 'session_id': sid}),
                           text=True, check=True, env=dict(self.env, CLAUDE_PROJECT_DIR=repo))
        lines = read(os.path.join(repo, '.cctime', 'events.jsonl')).splitlines()
        self.assertEqual([json.loads(l)['event'] for l in lines], ['UserPromptSubmit', 'Stop'])
        self.write_events([ev(D, '10:00', 'UserPromptSubmit', 'c2'), ev(D, '10:45', 'Stop', 'c2')],
                          os.path.join(repo, '.cctime', 'events.jsonl'))
        out = self.report('--from', D, '--to', D)
        self.assertEqual(rows(out)[(D, 'Acme')][0], '0h45')   # project from the repo folder, not the event
        self.assertIn((D, 'old'), rows(out))      # the adopted legacy repo keeps being read


class LoggerTest(Sandbox):
    def test_logger_writes_to_cctime_home_and_never_fails(self):
        self.write_json('projects.json', {'~/work/acme': 'Acme'})
        cwd = os.path.join(self.tmp, 'work', 'acme', 'sub')
        os.makedirs(cwd)
        payload = json.dumps({'hook_event_name': 'SubagentStart', 'session_id': 's1', 'cwd': cwd, 'agent_id': 'a1',
                              'agent_type': 'Explore', 'prompt': 'secret prompt text'})
        self.run_script('cctime_log.py', stdin=payload)
        self.assertEqual(self.run_script('cctime_log.py', stdin='not json').returncode, 0)
        rec = read_json(os.path.join(self.home, 'events.jsonl'))
        self.assertEqual((rec['event'], rec['project'], rec['agent_id'], rec['agent_type']), ('SubagentStart', 'Acme', 'a1', 'Explore'))
        self.assertNotIn('secret', json.dumps(rec))

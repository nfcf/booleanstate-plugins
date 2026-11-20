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


def projects(path):
    with open(path) as f:
        return [json.loads(l)['project'] for l in f]


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

    def test_apply_relabels_past_events(self):
        events = os.path.join(self.home, 'events.jsonl')
        mapped = os.path.join(self.tmp, 'work', 'clientb', 'x')
        loose = os.path.join(self.tmp, 'play', 'toy')
        self.write_events([ev('2026-01-05', '09:00', 'UserPromptSubmit', 'a', 'x', mapped),
                           ev('2026-01-05', '09:30', 'Stop', 'a', 'x', mapped),
                           ev('2026-01-05', '10:00', 'UserPromptSubmit', 'b', 'toy', loose)])
        rules = json.dumps({'~/work/clientb': 'Client B'})
        out = self.run_script('cctime_setup.py', 'diff', '--rules', rules).stdout
        self.assertIn('Would relabel 2 past events', out)
        self.assertIn('x -> Client B: 2', out)
        self.assertEqual(projects(events), ['x', 'x', 'toy'])
        out = self.run_script('cctime_setup.py', 'apply', '--rules', rules).stdout
        self.assertIn('Relabelled 2 past events', out)
        self.assertEqual(projects(events), ['Client B', 'Client B', 'toy'])
        self.assertEqual(len([f for f in os.listdir(self.home) if f.startswith('events.jsonl.bak-')]), 1)
        self.assertIn('No past events to relabel.', self.run_script('cctime_setup.py', 'diff').stdout)

    def test_gone_folder_not_relabelled_by_subfolder_name(self):
        self.write_json('projects.json', {'/elsewhere/acme/web': 'Acme', '/elsewhere/clientb-review': 'Client B'})
        self.write_events([ev('2026-01-05', '09:00', 'UserPromptSubmit', 'a', 'clientb-review', '/nonexistent/clientb-review/web'),
                           ev('2026-01-05', '09:05', 'UserPromptSubmit', 'b', 'other', '/nonexistent/other/web')])
        out = self.run_script('cctime_setup.py', 'diff').stdout
        self.assertIn('clientb-review -> Client B: 1', out)
        self.assertNotIn('Acme', out)

    def test_apply_without_rules_relabels_stale_events(self):
        self.write_json('projects.json', {'~/work': 'Other'})
        cwd = os.path.join(self.tmp, 'work')
        self.write_events([ev('2026-01-05', '09:00', 'UserPromptSubmit', 'a', 'work', cwd)],
                          path=os.path.join(self.home, 'backfill.jsonl'))
        out = self.run_script('cctime_setup.py', 'apply').stdout
        self.assertIn('No change to projects.json.', out)
        self.assertIn('work -> Other: 1', out)
        self.assertEqual(projects(os.path.join(self.home, 'backfill.jsonl')), ['Other'])
        self.assertEqual([f for f in os.listdir(self.home) if f.startswith('projects.json.bak-')], [])


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

    def test_worktree_resolves_like_its_main_checkout_under_a_catch_all(self):
        self.write_json('projects.json', {'~/work/acme': 'Acme', '~/work': 'Other'})
        repo = os.path.join(self.tmp, 'work', 'acme')
        worktree = os.path.join(self.tmp, 'work', 'acme-T-1')
        loose = os.path.join(self.tmp, 'work', 'loose')
        os.makedirs(loose)
        subprocess.run(['git', 'init', '-q', repo], check=True)
        subprocess.run(['git', '-C', repo, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '--allow-empty', '-m', 'x'], check=True)
        subprocess.run(['git', '-C', repo, 'worktree', 'add', '-q', worktree], check=True)
        for cwd in (worktree, loose):
            self.run_script('cctime_log.py', stdin=json.dumps({'hook_event_name': 'Stop', 'session_id': 's1', 'cwd': cwd}))
        self.assertEqual(projects(os.path.join(self.home, 'events.jsonl')), ['Acme', 'Other'])
        # once the worktree is removed, the stored main checkout keeps it from being relabelled to the catch-all
        subprocess.run(['git', '-C', repo, 'worktree', 'remove', worktree], check=True)
        self.assertIn('No past events to relabel.', self.run_script('cctime_setup.py', 'diff').stdout)

    def test_worktree_own_rule_beats_main_checkout_rule(self):
        self.write_json('projects.json', {'~/work': 'Other', '~/work/acme': 'Acme', '~/w/a': 'Explicit'})
        repo = os.path.join(self.tmp, 'work', 'acme')
        worktree = os.path.join(self.tmp, 'w', 'a')              # its rule is shorter than the main checkout's
        subprocess.run(['git', 'init', '-q', repo], check=True)
        subprocess.run(['git', '-C', repo, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '--allow-empty', '-m', 'x'], check=True)
        subprocess.run(['git', '-C', repo, 'worktree', 'add', '-q', worktree], check=True)
        self.run_script('cctime_log.py', stdin=json.dumps({'hook_event_name': 'Stop', 'session_id': 's1', 'cwd': worktree}))
        self.assertEqual(projects(os.path.join(self.home, 'events.jsonl')), ['Explicit'])
        subprocess.run(['git', '-C', repo, 'worktree', 'remove', worktree], check=True)
        self.assertIn('No past events to relabel.', self.run_script('cctime_setup.py', 'diff').stdout)

    def make_worktree(self, repo, worktree):
        subprocess.run(['git', 'init', '-q', repo], check=True)
        subprocess.run(['git', '-C', repo, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '--allow-empty', '-m', 'x'], check=True)
        subprocess.run(['git', '-C', repo, 'worktree', 'add', '-q', worktree], check=True)

    def test_relabel_records_main_on_older_worktree_events(self):
        self.write_json('projects.json', {'~/work/app': 'App', '~/work': 'Other'})
        repo, worktree = os.path.join(self.tmp, 'work', 'app'), os.path.join(self.tmp, 'work', 'app-T-1')
        self.make_worktree(repo, worktree)
        self.write_events([ev('2026-01-05', '09:00', 'Stop', 's1', 'Other', worktree)])   # logged before `main` existed
        self.assertIn('Other -> App: 1', self.run_script('cctime_setup.py', 'apply').stdout)
        with open(os.path.join(self.home, 'events.jsonl')) as f:
            self.assertEqual(json.loads(f.read())['main'], repo)
        subprocess.run(['git', '-C', repo, 'worktree', 'remove', worktree], check=True)
        self.assertIn('No past events to relabel.', self.run_script('cctime_setup.py', 'apply').stdout)

    def test_remap_uses_stored_main_of_removed_worktree(self):
        self.write_json('projects.json', {'~/work/app': 'App', '~/work': 'Other'})
        gone = os.path.join(self.tmp, 'work', 'app-T-1')
        self.write_events([ev('2026-01-05', '09:00', 'UserPromptSubmit', 's1', 'App', gone, main=os.path.join(self.tmp, 'work', 'app')),
                           ev('2026-01-05', '09:30', 'Stop', 's1', 'App', gone, main=os.path.join(self.tmp, 'work', 'app'))])
        self.assertEqual(list(rows(self.report('--from', '2026-01-05', '--to', '2026-01-05', '--remap'))), [('2026-01-05', 'App')])

    def test_main_checkout_through_a_symlink_is_not_a_worktree(self):
        real = os.path.join(self.tmp, 'real')
        repo, worktree = os.path.join(real, 'app'), os.path.join(real, 'app-T-1')
        self.make_worktree(repo, worktree)
        link = os.path.join(self.tmp, 'link'); os.symlink(real, link)
        self.write_json('projects.json', {link: 'Other', os.path.join(link, 'app'): 'App'})
        for cwd in (os.path.join(link, 'app'), os.path.join(link, 'app-T-1')):
            self.run_script('cctime_log.py', stdin=json.dumps({'hook_event_name': 'Stop', 'session_id': 's1', 'cwd': cwd}))
        with open(os.path.join(self.home, 'events.jsonl')) as f:
            recs = [json.loads(l) for l in f]
        self.assertEqual([r['project'] for r in recs], ['App', 'App'])
        self.assertNotIn('main', recs[0])
        self.assertEqual(recs[1]['main'], os.path.join(link, 'app'))

    def test_symlinked_worktree_folder_stores_a_real_main(self):
        repo, worktree = os.path.join(self.tmp, 'g', 'app'), os.path.join(self.tmp, 'g', 'wts', 'app-wt')
        self.make_worktree(repo, worktree)
        link = os.path.join(self.tmp, 'g', 'wtlink'); os.symlink(worktree, link)
        self.run_script('cctime_log.py', stdin=json.dumps({'hook_event_name': 'Stop', 'session_id': 's1', 'cwd': link}))
        with open(os.path.join(self.home, 'events.jsonl')) as f:
            self.assertEqual(json.loads(f.read())['main'], repo)

    def test_diff_reports_main_only_records_and_git_dir_is_ignored(self):
        self.write_json('projects.json', {'~/work/app': 'App'})
        repo, worktree = os.path.join(self.tmp, 'work', 'app'), os.path.join(self.tmp, 'work', 'wts', 'app-wt')
        self.make_worktree(repo, worktree)
        self.write_events([ev('2026-01-05', '09:00', 'Stop', 's1', 'App', worktree)])
        out = self.run_script('cctime_setup.py', 'diff').stdout
        self.assertIn('Would record the main checkout on 1 worktree events', out)
        self.assertIn('No past events to relabel.', out)
        self.env['GIT_DIR'] = os.path.join(repo, '.git')          # must not make every folder a worktree of it
        loose = os.path.join(self.tmp, 'loose'); os.makedirs(loose)
        self.run_script('cctime_log.py', stdin=json.dumps({'hook_event_name': 'Stop', 'session_id': 's2', 'cwd': loose}))
        with open(os.path.join(self.home, 'events.jsonl')) as f:
            self.assertNotIn('main', [json.loads(l) for l in f][-1])

    def test_setup_list_names_an_older_worktree_event_by_its_main_checkout(self):
        self.write_json('projects.json', {'~/work/other': 'Other'})
        repo, worktree = os.path.join(self.tmp, 'work', 'app'), os.path.join(self.tmp, 'work', 'app-T-1')
        self.make_worktree(repo, worktree)
        from datetime import date
        today = date.today().isoformat()
        self.write_events([ev(today, '00:01', 'UserPromptSubmit', 's1', 'app-T-1', worktree),   # no stored main
                           ev(today, '00:31', 'Stop', 's1', 'app-T-1', worktree)])
        unmapped = json.loads(self.run_script('cctime_setup.py', 'list').stdout)['unmapped']
        self.assertEqual([u['folder'] for u in unmapped], ['~/work/app'])

    def test_setup_list_names_a_worktree_by_its_main_checkout(self):
        self.write_json('projects.json', {'~/work/other': 'Other'})
        repo = os.path.join(self.tmp, 'work', 'app')
        worktree = os.path.join(self.tmp, 'work', 'app-T-1')
        subprocess.run(['git', 'init', '-q', repo], check=True)
        subprocess.run(['git', '-C', repo, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '--allow-empty', '-m', 'x'], check=True)
        subprocess.run(['git', '-C', repo, 'worktree', 'add', '-q', worktree], check=True)
        from datetime import date
        today = date.today().isoformat()
        self.write_events([ev(today, '00:01', 'UserPromptSubmit', 's1', 'app', worktree, main=repo),
                           ev(today, '00:31', 'Stop', 's1', 'app', worktree, main=repo)])
        unmapped = json.loads(self.run_script('cctime_setup.py', 'list').stdout)['unmapped']
        self.assertEqual([(u['folder'], u['logged_as']) for u in unmapped], [('~/work/app', 'app')])

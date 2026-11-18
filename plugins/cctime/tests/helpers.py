"""Test helpers: every script runs in a subprocess with HOME, CCTIME_HOME and TZ pointed at a temp dir,
so no test reads or writes real data."""
import json, os, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, 'scripts')


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix='cctime-test-'))
        self.home = os.path.join(self.tmp, '.cctime')
        os.makedirs(self.home)
        self.env = dict(os.environ, HOME=self.tmp, CCTIME_HOME=self.home, TZ='UTC',
                        CLAUDE_CONFIG_DIR=os.path.join(self.tmp, '.claude'))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_script(self, name, *args, ok=True, stdin=None):
        p = subprocess.run([sys.executable, os.path.join(SCRIPTS, name), *args], env=self.env, cwd=self.tmp,
                           capture_output=True, text=True, input=stdin)
        if ok and p.returncode != 0:
            self.fail(f'{name} {args} failed ({p.returncode}): {p.stderr}{p.stdout}')
        return p

    def write_events(self, events, path=None):
        path = path or os.path.join(self.home, 'events.jsonl')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'a') as f:
            for e in events:
                f.write(json.dumps(e) + '\n')

    def write_json(self, name, data):
        with open(os.path.join(self.home, name), 'w') as f:
            json.dump(data, f)

    def report(self, *args, pretty=False):
        """Numeric tests read the stable --plain layout; pretty=True gives the default layout."""
        return self.run_script('cctime_report.py', *args, *(() if pretty else ('--plain',))).stdout


def ev(day, hm, event, session='s1', project='Acme', cwd=None, **extra):
    r = {'ts': f'{day}T{hm}:00+00:00', 'event': event, 'session': session, 'project': project,
         'cwd': cwd or f'/nonexistent/{project}', 'branch': extra.pop('branch', None), 'ticket': extra.pop('ticket', None)}
    r.update(extra)
    return r


def rows(out):
    """{(date, project): [active, agent, review, manual, tickets]} from the report's table."""
    res = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 6 and len(parts[0]) == 10 and parts[0][4] == '-':
            res[(parts[0], parts[1])] = parts[2:6] + [' '.join(parts[6:])]
    return res


def total(out, label):
    for line in out.splitlines():
        if line.strip().startswith(label):
            return line.split()[-1]
    return None


def read(path):
    with open(path) as f:
        return f.read()


def read_json(path):
    return json.loads(read(path))

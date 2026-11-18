# cctime: billable time from your Claude Code sessions

cctime logs when you prompt Claude Code and when it stops, then reports time per client per day.
It is built for billing:

- **Agent and review time.** Time while Claude works plus the time you spend reading its answer before the next prompt.
- **No double counting.** Parallel sessions on the same client are merged. Different clients each get their own
  total, and the report prints wall-clock time and the parallel overlap so you can see the difference.
- **Clients by folder.** `~/Repos/acme` → `Acme`, longest prefix wins. `/cctime:setup` writes the mapping for you.
- **Tickets from branch names.** `feature/ABC-123-login` adds `ABC-123` to the day's row.
- **Dev containers.** Claude Code running inside a container is counted too.
- **Local only.** Nothing leaves your machine, and prompt text is never stored. Python 3.9+ standard library only.

## Install

    /plugin marketplace add <org>/booleanstate-plugins
    /plugin install cctime@booleanstate

Restart open Claude Code sessions so they pick up the hooks. The hooks run `python3`, so you need macOS or
Linux (Windows is untested; WSL should work).

## First run

    /cctime:backfill        # import past weeks from your existing Claude Code transcripts
    /cctime:setup           # assign folders to clients
    /cctime:report          # this week

## Skills

| Skill | What it does | Examples |
|---|---|---|
| `/cctime:report` | Time per client per day | `/cctime:report` · `today` · `last week round 15` · `this month` · `november csv ~/Desktop/nov.csv` · `last month remap` |
| `/cctime:add` | Manual time, list, undo | `/cctime:add Acme 45m standup` · `/cctime:add yesterday Acme 14:00-14:45 sprint review` · `list` · `undo` |
| `/cctime:setup` | Map unmapped folders to clients | `/cctime:setup` · `/cctime:setup 30` (look back 30 days) |
| `/cctime:backfill` | Import history from transcripts | `/cctime:backfill` · `since 2026-10-01` · `dry run` |
| `/cctime:container` | Log Claude Code inside a dev container | `/cctime:container ~/Repos/acme` · `list` |

The report also accepts Portuguese periods: `hoje`, `ontem`, `semana passada`, `este mês`, `mês passado`.

From a terminal, the scripts are in the installed plugin folder, e.g.
`python3 ~/.claude/plugins/cache/booleanstate/cctime/<version>/scripts/cctime_report.py --last-week`.
The folder changes with each version, so point aliases at a clone of this repo instead. Add `--plain` for the
compact one-line-per-row layout, which stays stable for scripts that read the output.

## What counts

- **agent**: from your prompt until Claude stops (capped at 90 min per run, `--max-run`).
- **subagents** (incl. background reviewers): from `SubagentStart` to `SubagentStop`, counted as agent time (same 90 min cap).
- **review**: from Claude stopping until your next prompt in that session, if within 10 min (`--idle`).
- **active** (billable per project): agent + review merged per project, so two sessions on the same project never double count.
- Different projects are counted separately; the report also prints wall-clock time and the parallel overlap.
- Branch names with Jira IDs (e.g. `feature/ABC-123-x`) are captured in the tickets column.
- `--round 15` rounds each client/day up to 15 minutes.

The client is resolved when an event is logged. If you change the mapping later, earlier events keep their old
name; run the report with `remap` (`--remap`) to re-resolve them from their folders. After the totals, the report
lists **Unmapped folders**: time in folders no rule covers, with a hint to run `/cctime:setup`.

## Manual time

Meetings, calls and anything else outside Claude Code go in `manual.csv`:

    /cctime:add Acme 45m client call            # 45 minutes ending now
    /cctime:add Acme 1h30 ending 12:00          # also 1h, 1.5h, 1h30m
    /cctime:add yesterday Acme 14:00-14:45 sprint review
    /cctime:add list                            # last 5 entries
    /cctime:add undo                            # remove the last entry

The project must match an existing client name exactly (from `projects.json` or earlier manual rows). A new name
is refused unless you confirm it, because a typo would show up as its own row. Entries cannot cross midnight.
A manual row that overlaps agent time on the same client is counted once.

## Backfill

`/cctime:backfill` reads `~/.claude/projects/*/*.jsonl` and creates a prompt event for each message you typed
and a stop event at Claude's last reply before your next prompt. It skips sessions the hooks already logged and
anything after the first hook event, so nothing is counted twice. It writes `backfill.jsonl`; delete that file to
undo, and running it again replaces it. Subagent (sidechain) time is not backfilled.

## Dev containers

Claude Code inside a container can't see `~/.cctime`, so it logs into the bind-mounted repo instead. Nothing in
the client's devcontainer config changes.

1. On your machine, once per repo: `/cctime:container ~/Repos/acme`. This copies a small `sh` logger into
   `<repo>/.cctime/`, hides it from git (`.git/info/exclude`) and registers the repo in `repos.json`.
2. Inside the container, once: `sh /workspaces/acme/.cctime/setup-container.sh` (adjust to your workspace path).
   The Claude config usually lives in a volume, so this survives rebuilds.
3. Restart Claude Code in the container.

Every session in that container counts under the repo's client, including git worktrees. The logger needs only
`sh` and stores time, event, session id and branch, never prompt text.

## Data files

Everything lives in `~/.cctime` (set `CCTIME_HOME` to use another folder):

| File | Contents |
|---|---|
| `events.jsonl` | One line per hook event (time, event, session, folder, client, branch, ticket, host) |
| `backfill.jsonl` | Events imported from transcripts (delete to undo the backfill) |
| `projects.json` | Folder prefix → client name (see `examples/projects.example.json`) |
| `manual.csv` | Manual entries: `date,project,start,end,note` |
| `repos.json` | Repos with a dev-container logger |
| `projects.json.bak-*` | Backups written by `/cctime:setup` |

Delete a file to remove that data, or `rm -rf ~/.cctime` to remove everything. Container logs are in
`<repo>/.cctime/`.

## Uninstall

    /plugin uninstall cctime@booleanstate

This removes the hooks and skills. Your data in `~/.cctime` is kept; delete it yourself if you want it gone.
In each repo you set up for a container, remove `.cctime/` and the cctime hooks from the container's
`~/.claude/settings.json`.

## Not included

Pause/resume, heartbeats from tool calls, a status line (plugins can't ship one), cloud sync, Windows support.

## Tests

    python3 -m unittest discover -s tests

## License

MIT

# BooleanState Claude Code plugins

A Claude Code plugin marketplace by [BooleanState](https://www.booleanstate.com/).

| Plugin | What it does |
|---|---|
| [cctime](plugins/cctime) | Billable time per client from your Claude Code sessions: agent and review time, parallel sessions never double counted, tickets from branch names, dev containers. Local only. |

## Install

In Claude Code, add the marketplace once, then install the plugins you want:

    /plugin marketplace add nfcf/booleanstate-plugins
    /plugin install cctime@booleanstate

Restart open Claude Code sessions so they pick up the plugin's hooks.

To get new versions later, run `/plugin marketplace update booleanstate`. From a clone, add the folder instead:
`/plugin marketplace add ~/path/to/booleanstate-plugins`.

## License

MIT

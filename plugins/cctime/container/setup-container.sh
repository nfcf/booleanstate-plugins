#!/bin/sh
# Run ONCE inside the dev container:  sh /workspace/.cctime/setup-container.sh
# Registers the cctime hooks in the container's Claude Code user settings (covers every
# session in the container, including git worktrees). Safe to run again.
here=$(cd "$(dirname "$0")" && pwd)
cfg="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json"
cmd="sh $here/log.sh"
mkdir -p "$(dirname "$cfg")"; [ -f "$cfg" ] || echo '{}' > "$cfg"
cp "$cfg" "$cfg.bak-cctime"
merge_py='
import json,sys
p,cmd=sys.argv[1],sys.argv[2]; c=json.load(open(p)); h=c.setdefault("hooks",{})
for ev in ("UserPromptSubmit","Stop","StopFailure","SessionStart","SessionEnd","SubagentStart","SubagentStop"):
    g=h.setdefault(ev,[])
    if not any(x.get("command")==cmd for grp in g for x in grp.get("hooks",[])):
        g.append({"hooks":[{"type":"command","command":cmd,"async":True}]})
json.dump(c,open(p,"w"),indent=2)'
merge_js='
const fs=require("fs");const[p,cmd]=process.argv.slice(1);const c=JSON.parse(fs.readFileSync(p,"utf8"));const h=c.hooks=c.hooks||{};
for(const ev of ["UserPromptSubmit","Stop","StopFailure","SessionStart","SessionEnd","SubagentStart","SubagentStop"]){const g=h[ev]=h[ev]||[];
 if(!g.some(grp=>(grp.hooks||[]).some(x=>x.command===cmd)))g.push({hooks:[{type:"command",command:cmd,async:true}]});}
fs.writeFileSync(p,JSON.stringify(c,null,2));'
if command -v python3 >/dev/null 2>&1; then python3 -c "$merge_py" "$cfg" "$cmd"
elif command -v node >/dev/null 2>&1; then node -e "$merge_js" "$cfg" "$cmd"
else echo "Need python3 or node to edit $cfg. Add this hook by hand (via /hooks): $cmd"; exit 1; fi
echo "cctime hooks registered in $cfg"
echo "Logging to $here/events.jsonl (visible on the Mac). Restart Claude Code sessions in this container."

# ARP dogfeed hook — portable bootstrap

Copy-paste this block into any skill, workflow, or agent prompt. An agent that
reads it can set up + register + run the vaked→ARP capture hook from scratch,
without any other doc.

[<arp-dogfeed-hook setup="idempotent">

GOAL: record substantial shell commands as validatable `arp_event` Vaked
declarations in `docs/arp-log.md`.

STEP 1 — schema (idempotent): ensure `vaked/schema/builtins.vaked` contains:
    schema arp_event {
      field ts      : String { required }
      field command : String { required nonempty }
      field inputs  : List<String> { optional }
      field outputs : List<String> { optional }
      field status  : String { required }
      field notes   : String { optional }
    }
Verify: `python3 -m vakedc check vaked/schema/builtins.vaked` → exit 0.

STEP 2 — hook: create `.claude/hooks/arp_log.py`, a PostToolUse handler that
reads stdin JSON and on `tool_name == "Bash"`:
  - skip if command matches trivial reads (ls/cat/echo/which/pwd/head/tail/cd,
    git status|log|diff|show|branch) OR contains ".vaked"|"vakedc"|"run_all.py";
  - keep a $TMPDIR/arp-gitmap.json stamp of `git status --porcelain -uall -z`;
    delta vs stamp = `outputs` (drop arp-log.md itself); advance stamp every run;
  - `inputs` = path-looking tokens in the command;
  - `status` = "ok" or "err: exit <n>: <stderr tail>" from `tool_response`
    (fields: exit_code|returncode, stderr, interrupted);
  - append a fenced block to `docs/arp-log.md`:
        ## YYYY-MM-DD HH:MM — <first 48 chars of command>

        ```vaked
        arp_event e_YYYYMMDD_HHMMSS {
          ts      = "YYYY-MM-DD HH:MM"
          command = "<command>"
          inputs  = ["..."]    # omit if empty
          outputs = ["..."]    # omit if empty
          status  = "ok"
        }
        ```
  - always exit 0; never block; instance name is an IDENT slug (not a string).
  (Reference implementation: `.claude/hooks/arp_log.py` in vaked-base.)

STEP 3 — register: add to `.claude/settings.json` under hooks.PostToolUse
(append, don't clobber):
    { "matcher": "Bash", "hooks": [ { "type": "command",
      "command": "python3 \"${CLAUDE_PROJECT_DIR:-.}/.claude/hooks/arp_log.py\"" } ] }

STEP 4 — verify the loop: `python3 tools/arp/verify_log.py docs/arp-log.md`
extracts the ```vaked fences, concatenates to a temp .vaked, runs
`python3 -m vakedc check`. Exit 0 = the log is provably valid Vaked.

INVARIANTS: zero grammar change (parser accepts any kind; checker binds
instance→schema by kind-name). Idempotent: re-running setup must not duplicate
the schema or the settings entry.

</arp-dogfeed-hook>]

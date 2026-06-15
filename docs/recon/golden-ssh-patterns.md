# golden remote-exec patterns (dev-cx53)

Hard-won. Use for every box command.

### 1. script over SSH without stdin-eating
- ✗ `ssh host 'bash -s' <<'EOF' … EOF` — an inner `sudo`/`bash -c` consumes the rest of the heredoc as *its* stdin → script silently truncated.
- ✓ `ssh host 'cat >/tmp/x.sh && bash /tmp/x.sh </dev/null' <<'EOF' … EOF` — `cat` drains the whole heredoc to a file; `bash file </dev/null` runs it with stdin nailed off.

### 2. timeouts
- macOS client has **no `timeout`** — never `timeout NN ssh …` (fails `command not found`).
- Bound remote commands with **remote** `timeout` (box has coreutils) + the harness/Bash-tool timeout as the outer guard.

### 3. `pkill`/`pgrep -f` self-match
- `pkill -f 'llama-server'` matches the launcher shell whose own cmdline contains `llama-server` → kills itself ("Terminated").
- Kill by **PID** from `ss -ltnp 'sport = :PORT'` or a pidfile — not by `-f` pattern. (`pgrep -f` skips its own pid but **not** the parent bash running it.)

### 4. revdev non-login shell (no banner, explicit PATH)
```
sudo -u revdev env PATH=/etc/profiles/per-user/revdev/bin:/run/current-system/sw/bin \
  HOME=/home/revdev bash -c '…' </dev/null
```

### 5. `uv` cwd
`uv` probes `./uv.toml` in CWD → from `/home/dev` that's perm-denied → `cd ~revdev/…` first.

### 6. transient tailnet drop → retry
`ssh -o ConnectTimeout=15 -o BatchMode=yes -o ServerAliveInterval=10 -o ServerAliveCountMax=3`; retry once on timeout.

### 7. bounded find
`find <root> -name X -print -quit` (stops at first hit) — never scan the whole `/nix/store`.

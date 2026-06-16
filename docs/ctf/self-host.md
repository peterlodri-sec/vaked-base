# Self-hosting the Vaked CTF arena

A small, **self-contained, open-source CTF game** you can stand up on your own machine or a
private box. Pure Python **standard library** — no pip installs, no database, no build step.
Licensed MIT (repo root [`LICENSE`](../../LICENSE)).

> 🔒 **Safety first.** The live arena and its targets are **tailnet-only by design** — the
> bind host is hard-gated to loopback or the Tailscale CGNAT range `100.64.0.0/10`. Two of
> the challenges are *intentionally vulnerable* practice boxes ([`vulnbox/`](../../tools/ctf/vulnbox/));
> they are contained (loopback, unprivileged, `realpath`-confined) and **must never be made
> public-facing**. This is authorized educational/CTF tooling, not a hardened service.

## Requirements

- Python **3.8+** (uses only the standard library).
- That's it. No dependencies, no network egress, no compiler.

## Quickstart (60 seconds, loopback)

```bash
git clone https://github.com/peterlodri-sec/vaked-base
cd vaked-base/tools/ctf
python3 ctf.py arena --with-boxes          # → http://127.0.0.1:8099
```

Open `http://127.0.0.1:8099`, pick a handle, solve a challenge, submit the flag. The
scoreboard updates live; `--with-boxes` launches the two real vulnbox targets on loopback so
the web/IDOR challenges are actually playable.

## Run on your tailnet (LAN of trusted machines)

```bash
python3 ctf.py arena --with-boxes --tailnet            # auto-bind this host's 100.x address
python3 ctf.py arena --with-boxes --host 100.105.72.88 # or bind an explicit tailnet IP
```

Players on the same [Tailscale](https://tailscale.com) tailnet reach it at
`http://<your-100.x>:8099`. The bind guard refuses `0.0.0.0` / public / LAN addresses, so you
cannot accidentally expose it to the internet.

## Persist + replay the scoreboard

```bash
python3 ctf.py arena --with-boxes --tailnet --ledger /var/lib/ctf/submissions.jsonl
```

Every correct submission is appended to a **hash-chained, append-only ledger**. The scoreboard
is a deterministic fold over that ledger — restart the server with the same `--ledger` and the
board is reconstructed exactly (`verify()` confirms the chain is intact). Tamper with a line
and verification fails.

## Run as a service (systemd)

A ready-to-edit unit ships at [`tools/ctf/ctf-arena.service`](../../tools/ctf/ctf-arena.service):

```bash
sudo cp tools/ctf/ctf-arena.service /etc/systemd/system/
sudoedit /etc/systemd/system/ctf-arena.service   # set User=, WorkingDirectory=, --host
sudo systemctl enable --now ctf-arena
```

The unit runs as an unprivileged user, binds a tailnet IP, persists the ledger, and hardens
the process (`NoNewPrivileges`, `ProtectSystem=strict`, `PrivateTmp`).

## The challenges

| id | category | pts | kind |
|----|----------|-----|------|
| `web-traversal` | web | 200 | real box — path traversal |
| `web-idor` | web | 150 | real box — IDOR |
| `crypto-caesar` | crypto | 100 | self-contained (ROT13) |
| `misc-base64` | misc | 75 | self-contained (base64) |
| `rev-xor` | rev | 125 | self-contained (single-byte XOR) |

First solver of each challenge earns a **first-blood bonus** (+50). Re-submitting a solved
challenge never double-counts.

## Add your own challenge

Edit [`tools/ctf/live_challenges.py`](../../tools/ctf/live_challenges.py) — append to
`CHALLENGES`:

```python
challenge("misc-rot47", "misc", 80, "FLAG{your_flag_here}",
          "hint shown to players", artifact="<puzzle text shown on the page>")
```

For a self-contained puzzle, derive `artifact` from the flag (see the `_rot13` / `_b64` /
`_xor_hex` helpers) so the puzzle and its answer can never drift. For a box-backed challenge,
pass `box={"module": "...", "solve": "...", ...}` and launch it in `live_server.launch_boxes()`.
Flags are checked constant-time (`hmac.compare_digest`).

## API (for bots / scripted players)

- `GET /scoreboard.json` → `{"ranking": [...], "scoreboard": [...]}`.
- `POST /submit` (form-encoded `handle`, `challenge`, `flag`) → `303` redirect; the result
  message is in the `msg` query param of the `Location`.
- `GET /healthz` → `ok`.

## Tests

```bash
cd tools/ctf
python3 test_live.py      # 15 — arena logic, ledger, live HTTP, full real-box loop
python3 test_web.py       # 11 — tailnet bind guard, render
python3 test_ctf.py       # 36 — the deterministic sim
python3 vulnbox/test_vulnbox.py   # 7 — the vulnerable boxes + containment
```

All standard-library, no test runner required.

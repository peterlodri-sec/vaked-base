# vulnbox — intentionally-vulnerable CTF lab targets

> ⚠️ **LAB ONLY. INTENTIONALLY VULNERABLE. LOOPBACK ONLY.**
> These programs contain *deliberate* security flaws for authorized educational/CTF
> practice on the vaked CTF range. Bind only to `127.0.0.1`, run only as an
> unprivileged user, and **never** expose them on a real network or host real data.

Two small, self-contained HTTP targets that bridge the abstract challenges in
[`../arena.py`](../arena.py) to *real* solvable boxes. Each box is one classic web
vulnerability, served by Python's stdlib `http.server` (no external deps).

| Box | File | Vuln class | Intended solution | Flag |
|-----|------|-----------|-------------------|------|
| traversal | `box_traversal.py` | Path traversal | `GET /file?name=../flag.txt` | `FLAG{tr4v3rs4l_b3y0nd_www}` |
| idor | `box_idor.py` | IDOR / broken access control | `GET /note?id=1337` (admin id hidden from `/notes`) | `FLAG{1d0r_4dm1n_n0t3_1337}` |

## Responsible-lab design (containment)

The vulns are real enough to learn from, but bounded so a target can't harm the host:

- **Loopback only.** Both bind `127.0.0.1`. No `0.0.0.0`, no published port.
- **Unprivileged.** Run as a normal user; nothing needs root.
- **Traversal is contained.** `box_traversal` has the deliberate bug (no input
  sanitization on `name`) **but** the resolved path is `realpath`-confined to the
  per-run `lab_root`. So `../flag.txt` escapes the served `www/` to the planted flag
  (the intended solve) while `../../../../etc/passwd` returns **403** — it cannot read
  the real host filesystem. The lab lives in a throwaway temp dir.
- **IDOR is self-contained.** `box_idor` holds an in-memory dict; no filesystem, no DB.

## Run a box (LAB ONLY, loopback)

```bash
python3 box_traversal.py /tmp/vulnbox-traversal 8071   # → http://127.0.0.1:8071
python3 box_idor.py 8072                                # → http://127.0.0.1:8072
```

## Capture the flags (intended solutions)

```python
import solve
solve.capture_traversal("http://127.0.0.1:8071")  # → 'FLAG{tr4v3rs4l_b3y0nd_www}'
solve.capture_idor("http://127.0.0.1:8072")        # → 'FLAG{1d0r_4dm1n_n0t3_1337}'
```

## Tests

```bash
python3 test_vulnbox.py     # boxes on ephemeral loopback ports; asserts capture + containment
```

Tests cover: each flag captured via its intended path, the traversal containment guard
(host-fs escape → 403), the IDOR listing hiding the admin id, and the admin note still
being directly readable (the vuln itself).

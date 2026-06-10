# tools/specdash — spec-verification dashboard

Generates a single self-contained `index.html` showing spec-test status for
`peterlodri-sec/vaked-base`. Combines live GitHub Actions run history with a
local run of `tests/spec/run_all.py` so you can see CI trends and local state
in one view.

## What it shows

- **Latest per ref** — one card per tag/branch (most recent run each).
- **Local suite** — runs `tests/spec/run_all.py` and renders the per-module table.
- **Run history** — last ~30 GitHub Actions runs with conclusion, duration, sha.

## How to run

```
python3 tools/specdash/build.py            # write tools/specdash/index.html
python3 tools/specdash/build.py --serve    # write + serve at http://localhost:8731
python3 tools/specdash/build.py --open     # write + open in browser (macOS)
```

## Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--out PATH` | `tools/specdash/index.html` | Output file path |
| `--serve [PORT]` | 8731 | Write then serve via http.server |
| `--open` | off | Open file/URL with `open` (macOS) |
| `--no-local` | off | Skip running the local spec suite |
| `--no-github` | off | Skip GitHub API calls |

## Notes

- Uses your local `gh` CLI auth. The repo is private; nothing is published.
- `index.html` is `.gitignore`d — it is a generated artifact.
- No external dependencies; Python 3 stdlib only.

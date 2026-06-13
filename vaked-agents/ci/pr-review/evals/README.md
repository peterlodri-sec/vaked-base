# Eval fixtures

Each `<name>.diff` is a tiny diff with a known issue; `<name>.expect` lists
newline-separated substrings the review must contain (case-insensitive). Run:

```bash
OPENROUTER_API_KEY=sk-or-... \
  cargo run --manifest-path vaked-agents/ci/pr-review/Cargo.toml -- --eval vaked-agents/ci/pr-review/evals
```

Keep expectations to robust, high-signal substrings (e.g. `unwrap`, `except`) so
the score tracks review quality, not phrasing. Add fixtures as real misses surface.

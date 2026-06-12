# Ralph Tracks — Implementation Plan

> **For agentic workers:** implement task-by-task; each task is TDD
> (failing test → code → green → commit). Checkbox (`- [ ]`) syntax tracks
> progress. **Spec:** `docs/superpowers/specs/2026-06-12-ralph-tracks-design.md`.
> **Tracking:** issue #34. **Branch:** `claude/autonomous-raw-loops-j93ilb`.

**Goal:** evolve `tools/ralph/` from a repo round-robin into **per-model
concept tracks** — `tracks.json` replaces `repos.json` as the primary axis, one
OpenRouter model pinned per track (both stages), CI-cron host that commits the
hash-chained `events.jsonl`, optional `uv`-managed Langfuse tracing, and an
append-only human ratify workflow.

**Invariants preserved:** `ralphcore.py` stays **pure stdlib** (Langfuse lives
only in `ralph.py`, optional-import). Read-only on all inputs except appends to
`docs/decisions/*` and `state/events.jsonl`. Budget/iteration caps remain
non-bypassable. `--repo`/`repos.json` kept working but **deprecated**.

---

## Phase 1 — Config + pure core (no behaviour change to live calls)

### Task 1.1 — `tracks.json` + `Track` + `load_tracks`

**Files:** create `tools/ralph/tracks.json`; modify `ralphcore.py`; test
`test_ralph.py`.

- [ ] **Write `tracks.json`** — the four tracks from the spec
      (`base-language-spec`, `graph-concept`, `mlir-topology`, `hcp-litany`),
      each `{name, topic, model, label, context:{docs:[...], paths:[...]}}`.
- [ ] **Failing test:**

```python
def test_load_tracks_parses_fields():
    cfg = {"tracks": [{"name": "t", "topic": "T", "model": "x/y",
            "label": "track:t", "context": {"docs": ["a/**"], "paths": ["a/"]}}]}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(cfg, fh); p = fh.name
    tracks = C.load_tracks(p)
    assert len(tracks) == 1
    t = tracks[0]
    assert t.name == "t" and t.model == "x/y" and t.label == "track:t"
    assert t.context.docs == ["a/**"] and t.context.paths == ["a/"]
```

- [ ] **Implement** in `ralphcore.py` (additive — keep `Repo`/`load_repos`):

```python
@dataclass(frozen=True)
class TrackContext:
    docs: list[str]
    paths: list[str]

@dataclass(frozen=True)
class Track:
    name: str
    topic: str
    model: str
    label: str
    context: TrackContext

def load_tracks(config_path: str) -> list[Track]:
    with open(config_path, encoding="utf-8") as f:
        data = json.load(f)
    out = []
    for t in data["tracks"]:
        c = t.get("context", {})
        out.append(Track(name=t["name"], topic=t["topic"], model=t["model"],
                         label=t.get("label", ""),
                         context=TrackContext(docs=list(c.get("docs", [])),
                                              paths=list(c.get("paths", [])))))
    return out
```

- [ ] Green; commit `feat(ralph): tracks.json + Track + load_tracks`.

### Task 1.2 — `next_track` (round-robin, reuse)

**Files:** `ralphcore.py`, `test_ralph.py`.

- [ ] **Failing test** — same semantics as `next_repo` (advance, wrap,
      skip-unavailable, first-run, all-unavailable→None):

```python
def test_next_track_advances_wraps_skips():
    names = ["a", "b", "c"]
    assert C.next_track(names, "a", set()) == "b"
    assert C.next_track(names, "c", set()) == "a"
    assert C.next_track(names, None, set()) == "a"
    assert C.next_track(names, "a", {"b"}) == "c"
    assert C.next_track(names, "a", {"a","b","c"}) is None
```

- [ ] **Implement** — `next_track = next_repo`'s algorithm. Make `next_repo`
      delegate to a shared `_next_in_ring(names, current, unavailable)` and
      define both `next_repo`/`next_track` as thin aliases (keeps the existing
      `test_next_repo_*` tests green, no duplication).
- [ ] Green; commit `feat(ralph): next_track round-robin (shared ring)`.

### Task 1.3 — topic-keyed prompts

**Files:** `ralphcore.py`, `test_ralph.py`.

- [ ] **Failing test:**

```python
def test_stage1_topic_keyed():
    msgs = C.build_stage1_messages("the Vaked grammar", "STATE", ["Prior X"])
    blob = json.dumps(msgs)
    assert "the Vaked grammar" in blob and "Prior X" in blob and "candidates" in blob
```

- [ ] **Implement** — generalise the system strings from `{repo} repository`
      to `{subject}`; `build_stage1_messages`/`build_stage2_messages` take a
      `subject` string (the repo name OR the track topic). Callers pass
      `track.topic` (tracks) or `repo.name` (deprecated repo path). Keep the
      `mission=` preamble param. Update the two existing prompt tests to the new
      signature (subject-positional).
- [ ] Green; commit `feat(ralph): subject-keyed stage prompts (repo|topic)`.

### Task 1.4 — prices for the new models

**Files:** `ralphcore.py`, `test_ralph.py`.

- [ ] Add `tencent/hy3-preview` and `xiaomi/mimo-v2.5` to `FALLBACK_PRICES`
      (placeholder rates + a `# refresh from /models` note); test that every
      track model resolves to a `Price` (no silent `KeyError`/guess):

```python
def test_every_track_model_has_price():
    for t in C.load_tracks(TRACKS_JSON):
        assert t.model in C.FALLBACK_PRICES, f"add price for {t.model}"
```

- [ ] Green; commit `feat(ralph): fallback prices for hy3-preview + mimo-v2.5`.

---

## Phase 2 — Per-track context + single-model `decide`

### Task 2.1 — track context gathering (scoped, read-only)

**Files:** `ralph.py`, `test_ralph.py`.

- [ ] **Implement `gather_track_context(track, git_log_window, compact)`** in
      `ralph.py`, reading **inside `REPO_HOME` (vaked-base)** only:
  - **Issues:** `gh issue list --repo peterlodri-sec/vaked-base --state open
    --label <track.label> --json number,title,body`; if the label yields zero
    and isn't a known repo label, fall back to all-open with a noted header.
  - **Docs:** expand `track.context.docs` globs against `REPO_HOME`
    (stdlib `glob`), concatenate (compact = `[:1500]` head per file; full =
    whole text).
  - **Git log:** `git log --oneline -n<window> -- <track.context.paths>`
    (empty `paths` → repo-wide).
- [ ] **Test (pure-ish, temp tree)** — point `REPO_HOME` at a temp dir with a
      couple of docs; assert glob scoping selects the right files and that an
      empty `paths` doesn't crash. (Issue/git reads are stubbed/skipped.)
- [ ] Commit `feat(ralph): per-track scoped context gathering`.

### Task 2.2 — single-model two-stage decide

**Files:** `ralph.py`, `test_ralph.py`.

- [ ] **Refactor `_decide_live`** to take an explicit `model` (used for **both**
      stages) and a `subject` (track topic) + `log_key` (track name), instead of
      `args.stage1_model`/`args.stage2_model`. The repo path passes
      `model=DEFAULT_S2`/`stage1=DEFAULT_S1` via a thin shim so the deprecated
      two-model behaviour is unchanged.
- [ ] **Test** — stub `openrouter_call` to record the `model` arg; assert a
      track decide calls it with `track.model` on **both** stages:

```python
def test_track_decide_uses_track_model_both_stages(monkeypatch):
    seen = []
    monkeypatch.setattr(R, "openrouter_call",
        lambda model, *a, **k: (seen.append(model), STUB_RESP)[1])
    R._decide_track(args, track_with_model("x/y"), api_key="k")
    assert seen == ["x/y", "x/y"]
```

- [ ] Keep the `_message_content` guard (thinking-only / empty responses).
- [ ] Commit `feat(ralph): single-model two-stage track decide`.

### Task 2.3 — `decide --track` / `--next-track` + per-track logs

**Files:** `ralph.py`, `test_ralph.py`.

- [ ] **CLI:** add `--track <name>` and `--next-track` to the `decide` parser
      (and `--tracks tracks.json`, default alongside `--repos`). `--repo` stays,
      marked deprecated in help text. Exactly one of `--track`/`--repo`/
      `--next-track` required.
- [ ] **`--next-track`** resolves the next track from the **event log**:
      `last_decided_track()` reads the last `decide` event's `track` field;
      `next_track(names, last, unavailable)` picks the next. (New helper in
      `ralph.py`; pure selection covered by Task 1.2.)
- [ ] **Per-track logs:** `docs/decisions/<track>.ralph-log.md`
      (`_log_path`/`_prior_titles` already key by name — pass `track.name`).
      Entry `**Models:**` line shows the single track model for both stages.
- [ ] **`--dry-run`** (no key, no network) prints the stage-1 prompt + estimate
      for a track — extend the existing dry-run smoke test to `--track`.
- [ ] Commit `feat(ralph): decide --track/--next-track + per-track logs`.

### Task 2.4 — supervisor over tracks

**Files:** `ralph.py`, `test_ralph.py`.

- [ ] **`cmd_run`** round-robins **tracks** by default (`--tracks`), `--repos`
      selects the deprecated repo mode. `_supervised_decide` folds per-track
      cost/last-title into `status` (keys become track names). `decide` events
      carry `{"event":"decide","track":<name>,...}`.
- [ ] **Dashboard:** `render_dashboard` column header `repo`→`track`, add a
      `model` column (read from `status["tracks"][name]["model"]`). Update the
      render unit test.
- [ ] **Budget-0 backstop** test carries over (zero calls, clean exit).
- [ ] Commit `feat(ralph): supervisor + dashboard over tracks`.

---

## Phase 3 — CI-cron host

### Task 3.1 — `pyproject.toml` (uv) skeleton

- [ ] `tools/ralph/pyproject.toml` declaring `langfuse` as the sole dep, Python
      `>=3.12`. `uv run --project tools/ralph …` syncs it. Core stays importable
      with zero deps. Commit `chore(ralph): uv pyproject (langfuse dep)`.

### Task 3.2 — workflow

- [ ] `.github/workflows/ralph-tracks.yml` per the spec sketch (verbatim
      decisions): `schedule: 0 */3 * * *` + `workflow_dispatch`;
      `concurrency: ralph-tracks`; `checkout@v4` with `fetch-depth: 0`;
      `uv run --project tools/ralph tools/ralph/ralph.py decide --next-track`;
      commit `docs/decisions/` + `state/events.jsonl` and push. Secrets:
      `OPENROUTER_API_KEY` (+ `LANGFUSE_*` when Phase 4 lands).
- [ ] Confirm `state/events.jsonl` is **not** gitignored (only `status.json`
      is) so the chain is committed; `ralph events --replay` verifies on any
      checkout.
- [ ] Commit `feat(ci): scheduled ralph-tracks decide + commit`.

> Manual verification: `workflow_dispatch` one run; confirm a `<track>.ralph-log.md`
> entry + an `events.jsonl` line are committed and the chain verifies.

---

## Phase 4 — Langfuse (optional import, uv-managed)

### Task 4.1 — span wrapper

- [ ] In `ralph.py`: `try: from langfuse import Langfuse / except ImportError:
      Langfuse = None`. A `_trace(model, track, kind)` context manager that is a
      no-op when `Langfuse is None`. Wrap each `openrouter_call`; record input
      (model, track, messages digest), output (usage, `cost_usd`, latency,
      finish reason). Trace id = `<track>#<N>`.
- [ ] **Test:** with `Langfuse=None`, `decide --dry-run` still passes (zero-dep
      invariant). Commit `feat(ralph): optional Langfuse spans`.

### Task 4.2 — live price refresh

- [ ] At supervisor start, fetch OpenRouter `/models`, override `FALLBACK_PRICES`
      for known ids (hardcoded fallback on failure). Commit
      `feat(ralph): live /models price refresh`.

---

## Phase 5 — Ratify workflow

### Task 5.1 — ratify-line parse (pure)

- [ ] **Failing test → implement** `parse_ratify_line` in `ralphcore.py`:

```python
def test_parse_ratify_line():
    line = "- graph-concept#3 — **override** — wrong layering — @pl 2026-06-12"
    r = C.parse_ratify_line(line)
    assert r == {"id": "graph-concept#3", "verdict": "override",
                 "reason": "wrong layering", "score": 0}
    assert C.parse_ratify_line("not a ratify line") is None
```

      (`ratify`→score 1, `override`/`defer`→0; malformed→None.)
- [ ] Commit `feat(ralph): ratify-line parser`.

### Task 5.2 — RATIFY.md (contributor guide)

- [ ] `docs/decisions/RATIFY.md`: what the loop is, how to read an entry, the
      three verdicts (ratify/override/defer), how to record one (append a line
      to `<track>.ratify-log.md`), and "what's next" (ratified → open a GitHub
      issue; the pass is triage, not implementation). No insider context assumed.
- [ ] Commit `docs(ralph): RATIFY.md contributor guide`.

### Task 5.3 — feedback loop

- [ ] Stage-1 context includes recent **override reasons** (from
      `<track>.ratify-log.md`) alongside prior titles, so the loop learns what
      the human rejects. When Langfuse is present, post the 0/1 ratify score on
      `<track>#<N>`. Commit `feat(ralph): override-reason feedback + ratify scores`.

---

## Definition of done

- `python3 tools/ralph/test_ralph.py` all-green (new + carried-over tests).
- `ralph decide --track base-language-spec --dry-run` prints a topic-scoped
  stage-1 prompt with no key/network.
- One real `--next-track` tick (with key) appends a grounded entry to the right
  `docs/decisions/<track>.ralph-log.md`, writes an `events.jsonl` line, chain
  verifies.
- The workflow runs on `workflow_dispatch` and commits the result.
- `--repo`/`repos.json` still runs (deprecated notice printed).

## Notes for the implementer

- **Additive, not destructive:** `Repo`/`load_repos`/`next_repo` and the
  two-model path stay; tracks are layered on. Removal of the repo path is a
  later, separate change after one release.
- **`ralphcore` purity:** no `datetime`, no network, no Langfuse. `ralph.py`
  owns all I/O.
- **Rotation has one source of truth:** the committed `events.jsonl`. Don't add a
  second pointer file.
- **Prices:** the two new models ship with placeholder rates — Task 4.2's live
  refresh is the real fix; flag if OpenRouter ids differ from the slugs here.

# dogfeedOS — Design Spec

**Date:** 2026-06-24  
**Status:** Approved  
**Repo target:** `peterlodri-sec/dogfeedOS` (new)

---

## Summary

dogfeedOS is an open-source, self-improving data loop that runs on a Raspberry Pi 3/4 (or any Docker-capable Linux). It generates Q&A pairs via free OpenRouter models, accumulates them locally, and optionally pushes them to a HuggingFace dataset. A lightweight web UI shows the live feed, budget status, and controls. The goal: anyone can clone, run `docker compose up`, and have a functioning data loop in under 3 minutes.

---

## 1. Architecture

Two containers. One shared SQLite volume. No build step for end users.

```
dogfeedOS/
  docker-compose.yml
  .env.example
  README.md

  services/
    loop/               ← container: "dogfeed"
      Dockerfile
      requirements.txt  ← requests, huggingface-hub only
      main.py           ← entrypoint
      loop.py           ← core loop (from dogfeed_loop.py)
      budget.py         ← daily call/token counter
      publisher.py      ← HF batch push
      ralph.py          ← reflection/self-steering pass
      db.py             ← all SQLite operations

    ui/                 ← container: "dogfeedui"
      Dockerfile
      requirements.txt  ← fastapi, uvicorn only
      server.py         ← API routes
      static/
        index.html      ← live dashboard
        setup.html      ← /setup wizard
        style.css       ← vaked dark theme

  data/                 ← Docker named volume (shared)
    dogfeed.db

  .github/
    workflows/
      build.yml         ← multi-arch image build on tag push
```

**Multi-arch images** on GHCR: `linux/arm/v7` (RPi 3), `linux/arm64` (RPi 4), `linux/amd64` (dev).

**Container memory** on RPi 4: ~80MB loop + ~60MB ui = ~140MB total.

---

## 2. Loop Engine

Each iteration:

1. Check budget → if limit hit, sleep until midnight UTC
2. Pick topic: from `LOOP_TOPICS` env (round-robin) OR `config.auto_topic` (from ralph pass) OR generate from previous answers
3. Call free OpenRouter model → generate question
4. Call free OpenRouter model → answer question
5. PII scrub + dedup check
6. Write record to SQLite
7. Increment budget counters
8. Every 50 records: trigger ralph reflection pass
9. If `HF_PUSH_EVERY` threshold reached: push to HuggingFace
10. Sleep `LOOP_INTERVAL_SEC`

**Model probing** — on startup, probe all configured models, remove non-responding, log working set. Round-robin across working models.

**Ralph reflection pass** (self-steering, runs async after every 50 records):

```python
last_50 = db.recent(50)
prompt = "Given these Q&A pairs about {topics}, what specific topic should
          we explore next that we haven't covered yet? One topic, no explanation."
next_topic = ask(prompt, free_model)
db.config_set("auto_topic", next_topic)
```

When `LOOP_TOPICS` is empty, the loop reads `auto_topic` from config. The loop generates its own direction from what it already knows — self-referencing, no human input needed.

---

## 3. Budget System

Transparent, enforced, user-configurable.

```bash
DAILY_CALL_LIMIT=200      # default: safe free tier
DAILY_TOKEN_LIMIT=50000   # default: safe free tier
LOOP_INTERVAL_SEC=30      # default: 30s between iterations
```

Counters in SQLite `budget` table. Reset at midnight UTC. Dashboard shows live bar with thresholds:
- < 80%: green
- 80–95%: amber
- > 95%: red + warning

When limit hit: loop sleeps, dashboard shows "paused — budget exhausted, resumes HH:MM UTC".

---

## 4. Web UI

**Theme:** `#070b16` bg, `#00d4ff` cyan, `#00e660` green, `ui-monospace` — matching G0DM0D3 + pocoo.vaked.dev aesthetic. Pure HTML/CSS, zero JS framework, zero build step.

### `/` — Dashboard

- Budget bars (calls + tokens, with reset countdown)
- Live feed: last N records (Q + truncated A, model, timestamp)
- Loop status: pulsing dot (running/paused/error)
- Pause/resume button (clean stop after current iteration)
- Dataset stats: total records, last HF push, manual push button
- "Load more" for older records

### `/setup` — First-Run Wizard

Four steps with inline validation:

1. **API Keys** — OpenRouter key (required, tested), HF token (optional, tested)
2. **Your Loop** — topics textarea, HF dataset repo (optional)
3. **Budget** — call limit, interval, push frequency
4. **Done** — writes to `config` table, redirects to dashboard in 3s

Wizard is available any time at `/setup`, not just first run. Config changes take effect on next loop iteration (no restart needed).

---

## 5. Data Schema

```sql
-- Every generated record
CREATE TABLE records (
    id            TEXT PRIMARY KEY,
    question      TEXT NOT NULL,
    answer        TEXT NOT NULL,
    q_model       TEXT,
    a_model       TEXT,
    topic         TEXT,
    timestamp     TEXT NOT NULL,
    iteration     INTEGER,
    answer_words  INTEGER,
    question_words INTEGER,
    pushed_to_hf  INTEGER DEFAULT 0
);

-- Daily budget, resets at midnight UTC
CREATE TABLE budget (
    date        TEXT PRIMARY KEY,
    calls       INTEGER DEFAULT 0,
    tokens      INTEGER DEFAULT 0,
    call_limit  INTEGER DEFAULT 200,
    token_limit INTEGER DEFAULT 50000
);

-- Runtime config (set by wizard or env)
CREATE TABLE config (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- Loop event log (last 100 entries)
CREATE TABLE events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    level   TEXT NOT NULL,    -- INFO / WARN / ERROR
    message TEXT NOT NULL
);
```

---

## 6. Deployment

### `.env.example`

```bash
# ── Required ────────────────────────────────────────────────
OPENROUTER_KEY=sk-or-v1-...

# ── Loop ─────────────────────────────────────────────────────
LOOP_TOPICS=machine learning,compilers,distributed systems
LOOP_INTERVAL_SEC=30

# ── Budget (free tier safe defaults) ─────────────────────────
DAILY_CALL_LIMIT=200
DAILY_TOKEN_LIMIT=50000

# ── HuggingFace (optional — leave blank to disable) ──────────
HF_TOKEN=
HF_REPO=
HF_PUSH_EVERY=50

# ── Server ───────────────────────────────────────────────────
UI_PORT=8080

# ── Models (comma-separated, probed on startup) ───────────────
OPENROUTER_MODELS=openai/gpt-oss-20b:free,liquid/lfm-2.5-1.2b-instruct:free
```

### `docker-compose.yml`

```yaml
services:
  dogfeed:
    image: ghcr.io/peterlodri-sec/dogfeedos-loop:latest
    restart: unless-stopped
    env_file: .env
    volumes:
      - data:/data

  ui:
    image: ghcr.io/peterlodri-sec/dogfeedos-ui:latest
    restart: unless-stopped
    env_file: .env
    ports:
      - "${UI_PORT:-8080}:8080"
    volumes:
      - data:/data

volumes:
  data:
```

### Getting started

```bash
git clone https://github.com/peterlodri-sec/dogfeedOS
cd dogfeedOS
cp .env.example .env
# edit .env: add OPENROUTER_KEY at minimum
docker compose up
# open http://localhost:8080/setup
```

### CI/CD

`.github/workflows/build.yml` — on push to `main` or tag: build multi-arch images, push to GHCR. Contributors can run locally with `docker compose build`.

---

## 7. Design Principles

**One job per file.** Want to change the loop interval logic? Touch only `loop.py`. Want to add Parquet export? Touch only `publisher.py`. No magic, no cross-file coupling.

**No build step for end users.** Pre-built GHCR images. Contributors build locally.

**Env file is the whole config surface.** Nothing hidden in code. All tunable values in `.env.example` with comments.

**Budget by default.** The loop cannot run unbounded. The daily limit ships enabled. Users who want unlimited must explicitly set `DAILY_CALL_LIMIT=0`.

**Self-steering when untended.** With `LOOP_TOPICS` empty, the ralph reflection pass generates the next topic from what the loop already knows. Leave it running — it finds its own direction.

---

## Out of Scope (v1)

- Local Ollama inference (v2: optional container)
- Multi-node / swarm mode
- Authentication on the web UI (local network assumed)
- Parquet export (use the existing `hf_optimize.py` from ultrawhale)
- Mobile app

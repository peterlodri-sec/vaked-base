# vaked-telebot — interactive Telegram control surface

The fleet *posts* to Telegram (yardmaster broadcasts). **telebot is the other
direction**: a long-poll daemon that lets an operator **drive** the fleet from the
`vaked` group — pick a scenario from a menu, or just ask in natural language.

## Scenarios (`/menu`)

| Button | Does |
|--------|------|
| 🚂 Merge train | yardmaster's current train — the per-PR plan + the signed infographic |
| 🩺 CI & PRs | open PRs with mergeable state + CI verdict |
| ⚙️ Trigger workflow | dispatch a workflow: nix-check / spec-tests / merge-train tick / ralph |
| 📚 Fleet & decisions | ralph's latest decisions + recent merges |

Send **any other text** and an OpenRouter model answers about the repo/fleet
(it's given a compact snapshot of the open PRs as context).

## Safety (the bot has admin in the chat)

- **Read** scenarios (train / CI / fleet) are allowed to the configured chat.
- **Acting** scenarios (⚙️ workflow dispatch) require the sender's Telegram user
  id to be in **`TELEGRAM_ADMIN_IDS`** — the guardrail, since the bot itself holds
  admin rights. A non-admin tap is denied and **never dispatches**.
- Every dispatch is appended to the `eventd` ledger (`state/log.jsonl`).
- Find your numeric id by messaging `@userinfobot` (or the "Get ID" bot).

## Run (self-hosted, crabcc.app plane)

It's a **long-poll daemon** (instant replies). Deploy on the crabcc.app host with
the included systemd unit:

```bash
sudo cp tools/telebot/vaked-telebot.service /etc/systemd/system/
sudoedit /etc/vaked-telebot.env        # see below (chmod 600)
sudo systemctl enable --now vaked-telebot
journalctl -u vaked-telebot -f
```

`/etc/vaked-telebot.env`:

```ini
TELEGRAM_TOKEN=123:abc            # @vakedAIcrabcc_bot
TELEGRAM_TO=-5386943266           # the vaked group
TELEGRAM_ADMIN_IDS=111111111      # comma-separated; who may trigger workflows
GITHUB_TOKEN=ghp_...              # repo + actions:write (for dispatch)
GITHUB_REPOSITORY=peterlodri-sec/vaked-base
OPENROUTER_API_KEY=sk-or-...      # or TELEBOT_API_KEY; free-form ask
# TELEBOT_MODEL=deepseek/deepseek-v4-flash   # optional override
```

Or run it directly: `python3 tools/telebot/telebot.py` with the same env.

## Design

`handle_update(Update, Ctx) -> [Op]` is a **pure function** — the Telegram /
GitHub / OpenRouter I/O is injected via `Ctx`, so the router (authz, menu,
callback routing, dispatch gating, free-form) unit-tests offline with no network
([`tests/spec/test_telebot.py`](../../tests/spec/test_telebot.py), in
`run_all.py`). The daemon long-polls `getUpdates`, routes each update, and
executes the returned Ops; one bad update never kills the loop; the poll offset
is persisted in `state/`.

Reuse (no new machinery): yardmaster's GitHub REST client + `fetch_prs`/
`plan_train`, `report` for the infographic, `eventd` for the action ledger.
Stdlib only otherwise.

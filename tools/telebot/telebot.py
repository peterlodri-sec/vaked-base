"""vaked-telebot — an interactive Telegram control surface for the agent fleet.

The fleet already *posts* to Telegram (yardmaster broadcasts). This is the other
direction: a long-poll daemon that lets an operator **drive** the fleet from the
`vaked` group — pick a scenario from a menu, or just ask in natural language.

Scenarios (the /menu inline keyboard):
  🚂 Merge train      — yardmaster's current train (plan + signed infographic)
  🩺 CI & PRs         — open PRs with mergeable state + CI verdict
  ⚙️ Trigger workflow — dispatch nix-check / vaked slice / spec-tests / merge-train
  📚 Fleet & decisions — ralph's latest decisions + recent merges
Free-form text (non-command) → an OpenRouter model answers about the repo/fleet.

SAFETY: the bot has admin in the chat, so **acting** commands (workflow dispatch)
require the sender to be in ``TELEGRAM_ADMIN_IDS``; read-only scenarios are allowed
to the configured chat. Every action is appended to the eventd ledger.

Design: the update router (:func:`handle_update`) is a PURE function of an
``Update`` + an injected :class:`Ctx` (github / llm / now) returning a list of
``Op`` (the messages/photos/dispatches to perform) — so it unit-tests offline with
no Telegram or GitHub I/O. The daemon long-polls getUpdates and executes the Ops.

Runtime: a long-poll daemon (instant replies) for the self-hosted crabcc.app plane
(systemd unit: vaked-telebot.service). Stdlib only + reuse (yardmaster, report,
eventd). Credentials from the `ci` Environment / the daemon's env.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for p in (REPO_ROOT, os.path.join(REPO_ROOT, "tools", "yardmaster")):
    if p not in sys.path:
        sys.path.insert(0, p)

STATE_DIR = os.path.join(HERE, "state")
OFFSET_PATH = os.path.join(STATE_DIR, "offset")
LOG_PATH = os.path.join(STATE_DIR, "log.jsonl")

TG_API = "https://api.telegram.org"
DEFAULT_MODEL = "deepseek/deepseek-v4-flash"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Scenario menu: (callback_data, button label). Acting scenarios are gated.
MENU = [
    ("train", "🚂 Merge train"),
    ("ci", "🩺 CI & PRs"),
    ("wf", "⚙️ Trigger workflow"),
    ("fleet", "📚 Fleet & decisions"),
]
# Workflows offered by the ⚙️ submenu: callback suffix → (workflow file, label).
WORKFLOWS = {
    "nix-check": ("spec-tests.yml", "🧊 nix flake check"),
    "spec": ("spec-tests.yml", "🧪 spec-tests"),
    "train": ("merge-train.yml", "🚂 merge-train tick"),
    "ralph": ("ralph-tracks.yml", "🧠 ralph decision"),
}
ACTING = {"wf"}        # callback prefixes that change state → require admin


# --------------------------------------------------------------------------- #
# Pure model.
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Update:
    """The slice of a Telegram update we route on."""
    chat_id: int
    user_id: int
    text: str = ""               # message text (commands / free-form)
    callback_id: str = ""        # set for a button tap
    callback_data: str = ""      # the tapped button's data


@dataclass
class Op:
    """One thing to do in response (executed by the daemon; asserted in tests)."""
    kind: str                    # message | photo | answer | dispatch
    payload: dict = field(default_factory=dict)


@dataclass
class Ctx:
    """Injected dependencies (real in the daemon, fakes in tests)."""
    repo: str
    admin_ids: set
    chat_id: int                 # the authorized chat
    github: object = None        # has .list_open_prs/.ci_state/.dispatch/.recent_merges
    train: object = None         # callable() -> (text, png|None)
    llm: object = None           # callable(prompt, context) -> str
    decisions: object = None     # callable() -> str


def menu_markup() -> dict:
    return {"inline_keyboard": [[{"text": lbl, "callback_data": cb}] for cb, lbl in MENU]}


def wf_markup() -> dict:
    rows = [[{"text": lbl, "callback_data": "wf:" + k}] for k, (_f, lbl) in WORKFLOWS.items()]
    rows.append([{"text": "⬅️ Back", "callback_data": "menu"}])
    return {"inline_keyboard": rows}


def authorized(update: Update, ctx: Ctx, acting: bool) -> bool:
    """Read scenarios: must be the configured chat. Acting scenarios: the sender
    must also be an admin (the bot holds admin rights, so this is the guardrail)."""
    if update.chat_id != ctx.chat_id:
        return False
    if acting:
        return update.user_id in ctx.admin_ids
    return True


def _is_acting(data: str) -> bool:
    return data.split(":", 1)[0] in ACTING


# --------------------------------------------------------------------------- #
# Router — pure: Update + Ctx → [Op].
# --------------------------------------------------------------------------- #

def handle_update(u: Update, ctx: Ctx) -> list:
    if u.callback_data:
        return _handle_callback(u, ctx)
    return _handle_message(u, ctx)


def _deny(u: Update) -> list:
    return [Op("message", {"chat_id": u.chat_id,
                           "text": "⛔ not authorized for this action"})]


def _handle_message(u: Update, ctx: Ctx) -> list:
    if not authorized(u, ctx, acting=False):
        return _deny(u)
    text = (u.text or "").strip()
    if text in ("/start", "/menu", "/help"):
        body = ("🤖 yardmaster control — pick a scenario, or just ask me anything "
                "about the repo / fleet." if text != "/help" else
                "Commands: /menu · or send a question. Buttons: train, CI, workflows, fleet.")
        return [Op("message", {"chat_id": u.chat_id, "text": body,
                               "reply_markup": menu_markup()})]
    if not text or text.startswith("/"):
        return [Op("message", {"chat_id": u.chat_id, "text": "Use /menu, or ask a question."})]
    # free-form → LLM
    answer = "🧠 (LLM not configured)"
    if ctx.llm:
        try:
            answer = ctx.llm(text, _repo_context(ctx))
        except Exception as e:      # noqa: BLE001
            answer = "LLM error: %s" % e
    return [Op("message", {"chat_id": u.chat_id, "text": answer})]


def _handle_callback(u: Update, ctx: Ctx) -> list:
    data = u.callback_data
    acting = _is_acting(data)
    if not authorized(u, ctx, acting=acting):
        return [Op("answer", {"callback_query_id": u.callback_id, "text": "⛔ not authorized"})]
    ack = Op("answer", {"callback_query_id": u.callback_id})
    if data == "menu":
        return [ack, Op("message", {"chat_id": u.chat_id, "text": "Pick a scenario:",
                                    "reply_markup": menu_markup()})]
    if data == "train":
        return [ack] + _scenario_train(u, ctx)
    if data == "ci":
        return [ack, Op("message", {"chat_id": u.chat_id, "text": _scenario_ci(ctx)})]
    if data == "fleet":
        return [ack, Op("message", {"chat_id": u.chat_id, "text": _scenario_fleet(ctx)})]
    if data == "wf" or data.startswith("wf:"):
        if ctx.github is None:          # no GitHub dispatch → don't pretend it worked
            return [ack, Op("message", {"chat_id": u.chat_id,
                                        "text": "⚠️ workflow dispatch unavailable "
                                                "(GitHub not configured)"})]
        if data == "wf":
            return [ack, Op("message", {"chat_id": u.chat_id,
                                        "text": "⚙️ Which workflow?", "reply_markup": wf_markup()})]
        key = data.split(":", 1)[1]
        wf = WORKFLOWS.get(key)
        if not wf:
            return [ack, Op("message", {"chat_id": u.chat_id, "text": "unknown workflow"})]
        return [ack,
                Op("dispatch", {"workflow": wf[0], "ref": "main", "by": u.user_id, "key": key,
                                "label": wf[1], "chat_id": u.chat_id})]
    return [ack, Op("message", {"chat_id": u.chat_id, "text": "unknown action"})]


def _scenario_train(u: Update, ctx: Ctx) -> list:
    if not ctx.train:
        return [Op("message", {"chat_id": u.chat_id, "text": "train unavailable"})]
    text, png = ctx.train()
    if png:
        return [Op("photo", {"chat_id": u.chat_id, "photo": png, "caption": text[:1024]})]
    return [Op("message", {"chat_id": u.chat_id, "text": text})]


def _scenario_ci(ctx: Ctx) -> str:
    if not ctx.github:
        return "GitHub unavailable"
    try:
        prs = ctx.github.list_open_prs()
    except Exception as e:          # noqa: BLE001
        return "GitHub error: %s" % e
    if not prs:
        return "🩺 no open PRs"
    lines = ["🩺 open PRs (%d):" % len(prs)]
    for p in prs[:20]:
        lines.append("#%s %s — %s/%s" % (p.get("number"), (p.get("title") or "")[:48],
                                         p.get("mergeable_state", "?"), p.get("ci", "?")))
    return "\n".join(lines)


def _scenario_fleet(ctx: Ctx) -> str:
    out = []
    if ctx.decisions:
        try:
            out.append(ctx.decisions())
        except Exception as e:      # noqa: BLE001
            out.append("decisions error: %s" % e)
    if ctx.github:
        try:
            merges = ctx.github.recent_merges(5)
            out.append("recent merges:\n" + "\n".join("• " + m for m in merges))
        except Exception:
            pass
    return "\n\n".join(out) or "📚 (no fleet data)"


def _repo_context(ctx: Ctx) -> str:
    """A compact repo snapshot fed to the LLM for free-form asks."""
    bits = ["repo=" + ctx.repo]
    if ctx.github:
        try:
            prs = ctx.github.list_open_prs()
            bits.append("open_prs=" + ", ".join("#%s %s" % (p.get("number"),
                        (p.get("title") or "")[:40]) for p in prs[:15]))
        except Exception:
            pass
    return "\n".join(bits)


# --------------------------------------------------------------------------- #
# I/O — Telegram client, GitHub ops, OpenRouter, the daemon loop.
# --------------------------------------------------------------------------- #

def _tg(token: str, method: str, params: dict, files=None):
    url = "%s/bot%s/%s" % (TG_API, token, method)
    if files:
        body = bytearray()
        boundary = "----telebot" + os.urandom(8).hex()
        for k, v in params.items():
            body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                     % (boundary, k, v)).encode()
        for name, (fn, data, ctype) in files.items():
            body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n"
                     "Content-Type: %s\r\n\r\n" % (boundary, name, fn, ctype)).encode()
            body += data + b"\r\n"
        body += ("--%s--\r\n" % boundary).encode()
        req = urllib.request.Request(url, data=bytes(body))
        req.add_header("Content-Type", "multipart/form-data; boundary=" + boundary)
    else:
        req = urllib.request.Request(url, data=urllib.parse.urlencode(
            {k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
             for k, v in params.items()}).encode())
    try:
        with urllib.request.urlopen(req, timeout=70) as r:
            return json.loads(r.read())
    except Exception as e:                  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _openrouter(prompt: str, context: str) -> str:
    key = os.environ.get("TELEBOT_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return "🧠 (no OpenRouter key configured)"
    model = os.environ.get("TELEBOT_MODEL", DEFAULT_MODEL)
    sys_prompt = ("You are vaked-ai, the control bot for the Vaked agent-fleet repo. "
                  "Answer concisely (<120 words) about the repo/fleet using the context. "
                  "If the user wants an action, tell them which /menu button to tap.\n\n" + context)
    body = json.dumps({"model": model, "max_tokens": 400, "messages": [
        {"role": "system", "content": sys_prompt}, {"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(OPENROUTER_URL, data=body)
    req.add_header("Authorization", "Bearer " + key)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read())
        return d["choices"][0]["message"]["content"].strip()
    except Exception as e:                  # noqa: BLE001
        return "LLM error: %s" % e


class GitHubOps:
    """PR list (with mergeable+ci), workflow dispatch, recent merges — reusing
    yardmaster's REST client."""

    def __init__(self, token: str, repo: str):
        from yardmaster import GitHub
        self.gh = GitHub(token, repo)

    def list_open_prs(self) -> list:
        out = []
        for raw in self.gh.open_prs():
            full = self.gh.pr(raw["number"])
            out.append({"number": raw["number"], "title": full.get("title", ""),
                        "mergeable_state": full.get("mergeable_state", "?"),
                        "ci": self.gh.ci_state(full["head"]["sha"])})
        return out

    def dispatch(self, workflow: str, ref: str = "main"):
        return self.gh._req("POST", "/repos/%s/actions/workflows/%s/dispatches"
                            % (self.gh.repo, workflow), {"ref": ref})

    def recent_merges(self, n: int = 5) -> list:
        commits = self.gh._req("GET", "/repos/%s/commits?per_page=%d" % (self.gh.repo, n))
        return [(c.get("commit", {}).get("message", "").splitlines() or [""])[0][:64]
                for c in (commits if isinstance(commits, list) else [])]


def _train_snapshot(gh_ops: "GitHubOps") -> "tuple[str, bytes | None]":
    """Build yardmaster's train + signed infographic for the 🚂 scenario."""
    import report
    import yardmaster as ym
    prs = ym.fetch_prs(gh_ops.gh)
    planned = ym.plan_train(prs, "main")
    text = report.build_text(gh_ops.gh.repo, planned, "live", None)
    png = report.render_png(report.build_svg(gh_ops.gh.repo, planned, "live"))
    img, _ = report.finalize_image(png, gh_ops.gh.repo, os.environ.get("GITHUB_SHA", ""),
                                   "merge train")
    return text, img


def _ledger(payload: dict) -> None:
    try:
        from eventd import EventLog
        os.makedirs(STATE_DIR, exist_ok=True)
        with EventLog(LOG_PATH, writer=True) as log:
            log.append(payload)
    except Exception:
        pass


def execute(ops: list, token: str, gh_ops: "GitHubOps | None") -> None:
    # NB: messages are sent as PLAIN TEXT (no parse_mode) — bodies carry arbitrary
    # content (PR titles, commit subjects, LLM output) that would break Markdown
    # parsing and make Telegram silently drop the message.
    for op in ops:
        if op.kind == "message":
            p = dict(op.payload)
            if "reply_markup" in p:
                p["reply_markup"] = json.dumps(p["reply_markup"])
            _tg(token, "sendMessage", p)
        elif op.kind == "photo":
            p = dict(op.payload)
            png = p.pop("photo")
            _tg(token, "sendPhoto", {k: v for k, v in p.items()},
                files={"photo": ("train.png", png, "image/png")})
        elif op.kind == "answer":
            _tg(token, "answerCallbackQuery", op.payload)
        elif op.kind == "dispatch":
            chat = op.payload.get("chat_id")
            label = op.payload.get("label", op.payload["workflow"])
            ok = False
            if gh_ops:
                try:
                    gh_ops.dispatch(op.payload["workflow"], op.payload.get("ref", "main"))
                    ok = True
                except Exception as e:      # noqa: BLE001
                    if chat:
                        _tg(token, "sendMessage", {"chat_id": chat,
                            "text": "❌ dispatch of %s failed: %s" % (label, e)})
            if ok:
                _ledger({"kind": "telebot_dispatch", **op.payload})
                if chat:
                    _tg(token, "sendMessage", {"chat_id": chat,
                        "text": "🚀 dispatched %s (%s) on main" % (label, op.payload["workflow"])})


def _update_from(raw: dict) -> "Update | None":
    if "callback_query" in raw:
        cq = raw["callback_query"]
        msg = cq.get("message", {})
        return Update(chat_id=msg.get("chat", {}).get("id", 0),
                      user_id=cq.get("from", {}).get("id", 0),
                      callback_id=cq.get("id", ""), callback_data=cq.get("data", ""))
    if "message" in raw:
        m = raw["message"]
        return Update(chat_id=m.get("chat", {}).get("id", 0),
                      user_id=m.get("from", {}).get("id", 0), text=m.get("text", ""))
    return None


def _read_offset() -> int:
    try:
        return int(open(OFFSET_PATH).read().strip())
    except (OSError, ValueError):
        return 0


def _write_offset(o: int) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    open(OFFSET_PATH, "w").write(str(o))


def run_daemon() -> int:
    token = os.environ.get("TELEGRAM_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY", "peterlodri-sec/vaked-base")
    chat_id = int(os.environ.get("TELEGRAM_TO", "0") or "0")
    admins = {int(x) for x in os.environ.get("TELEGRAM_ADMIN_IDS", "").replace(" ", "").split(",") if x}
    gh_token = os.environ.get("GITHUB_TOKEN")
    if not token or not chat_id:
        sys.stderr.write("telebot: TELEGRAM_TOKEN and TELEGRAM_TO required\n")
        return 2
    gh_ops = GitHubOps(gh_token, repo) if gh_token else None
    ctx = Ctx(repo=repo, admin_ids=admins, chat_id=chat_id, github=gh_ops,
              train=(lambda: _train_snapshot(gh_ops)) if gh_ops else None,
              llm=_openrouter, decisions=None)
    offset = _read_offset()
    sys.stderr.write("telebot: long-polling as %s for chat %d (admins=%s)\n"
                     % (repo, chat_id, sorted(admins)))
    while True:
        resp = _tg(token, "getUpdates",
                   {"offset": offset, "timeout": 50,
                    "allowed_updates": ["message", "callback_query"]})
        for raw in resp.get("result", []):
            offset = max(offset, raw["update_id"] + 1)
            up = _update_from(raw)
            if up is None:
                continue
            try:
                ops = handle_update(up, ctx)
                execute(ops, token, gh_ops)
            except Exception as e:          # noqa: BLE001 — one bad update never kills the loop
                sys.stderr.write("telebot: update error: %s\n" % e)
        _write_offset(offset)
        if not resp.get("ok", True):
            time.sleep(5)                   # back off on API error


if __name__ == "__main__":
    sys.exit(run_daemon())

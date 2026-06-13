#!/usr/bin/env python3
"""test_telebot.py — the interactive Telegram control bot's pure router.

No network: exercises the authz gate, the scenario menu, callback routing
(train / CI / workflow-dispatch / fleet), the free-form→LLM path, and the
unauthorized-deny paths — all through :func:`telebot.handle_update`, which is a
pure function of an ``Update`` + an injected ``Ctx`` (fake github / llm). The
Telegram + GitHub + OpenRouter I/O is not exercised here.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "tools", "telebot"))

import telebot as tb                       # noqa: E402

CHAT = 100
ADMIN = 7
STRANGER = 9


class _GH:
    def list_open_prs(self):
        return [{"number": 90, "title": "thing", "mergeable_state": "clean", "ci": "success"}]
    def recent_merges(self, n=5):
        return ["feat: x", "fix: y"]
    def dispatch(self, wf, ref="main"):
        self.dispatched = (wf, ref)


def _ctx(**kw):
    base = dict(repo="o/r", admin_ids={ADMIN}, chat_id=CHAT, github=_GH(),
                train=lambda: ("🚂 train text", None), llm=lambda p, c: "answer:" + p,
                decisions=lambda: "decisions")
    base.update(kw)
    return tb.Ctx(**base)


def _msg(text, user=ADMIN, chat=CHAT):
    return tb.Update(chat_id=chat, user_id=user, text=text)


def _cb(data, user=ADMIN, chat=CHAT):
    return tb.Update(chat_id=chat, user_id=user, callback_id="cq1", callback_data=data)


def _kinds(ops):
    return [o.kind for o in ops]


# --------------------------------------------------------------------------- #

def _test_menu_and_authz(lines):
    ok = True
    ops = tb.handle_update(_msg("/menu"), _ctx())
    if not ops or ops[0].kind != "message" or "reply_markup" not in ops[0].payload:
        ok = False
        lines.append("  FAIL menu: /menu should send a message with the keyboard")
    else:
        rows = ops[0].payload["reply_markup"]["inline_keyboard"]
        cbs = {r[0]["callback_data"] for r in rows}
        if cbs != {c for c, _ in tb.MENU}:
            ok = False
            lines.append(f"  FAIL menu: buttons {cbs} != {[c for c,_ in tb.MENU]}")
    # wrong chat → denied
    ops = tb.handle_update(_msg("/menu", chat=999), _ctx())
    if not ops or "not authorized" not in ops[0].payload.get("text", ""):
        ok = False
        lines.append("  FAIL authz: message from a foreign chat should be denied")
    if ok:
        lines.append("  PASS menu+authz: /menu renders the scenario keyboard; foreign chat denied")
    return ok


def _test_read_scenarios(lines):
    ok = True
    # CI scenario (read) — allowed even for non-admins in the right chat
    ops = tb.handle_update(_cb("ci", user=STRANGER), _ctx())
    if _kinds(ops) != ["answer", "message"] or "#90" not in ops[1].payload["text"]:
        ok = False
        lines.append(f"  FAIL ci: expected answer+PR list, got {ops}")
    # train scenario → photo when png present, else message
    ops = tb.handle_update(_cb("train"), _ctx(train=lambda: ("t", b"\x89PNG..")))
    if "photo" not in _kinds(ops):
        ok = False
        lines.append("  FAIL train: png present should yield a photo op")
    ops = tb.handle_update(_cb("train"), _ctx(train=lambda: ("t", None)))
    if "message" not in _kinds(ops):
        ok = False
        lines.append("  FAIL train: no png should yield a message op")
    # fleet
    ops = tb.handle_update(_cb("fleet"), _ctx())
    if "decisions" not in ops[1].payload["text"]:
        ok = False
        lines.append("  FAIL fleet: should include decisions")
    if ok:
        lines.append("  PASS read scenarios: CI list, train photo/text, fleet — read-open in chat")
    return ok


def _test_workflow_dispatch_gated(lines):
    ok = True
    # admin taps a workflow → answer + dispatch + confirmation message
    ops = tb.handle_update(_cb("wf:nix-check", user=ADMIN), _ctx())
    kinds = _kinds(ops)
    if "dispatch" not in kinds:
        ok = False
        lines.append(f"  FAIL wf: admin dispatch missing ({kinds})")
    else:
        disp = [o for o in ops if o.kind == "dispatch"][0]
        if disp.payload["workflow"] != tb.WORKFLOWS["nix-check"][0]:
            ok = False
            lines.append("  FAIL wf: wrong workflow file dispatched")
    # NON-admin taps a workflow → denied, NO dispatch
    ops = tb.handle_update(_cb("wf:nix-check", user=STRANGER), _ctx())
    if any(o.kind == "dispatch" for o in ops):
        ok = False
        lines.append("  FAIL wf: non-admin must NOT dispatch (acting gate)")
    if not ops or "not authorized" not in ops[0].payload.get("text", ""):
        ok = False
        lines.append("  FAIL wf: non-admin should get a deny answer")
    # GitHub unavailable → no dispatch op, an explicit 'unavailable' message (no false success)
    ops = tb.handle_update(_cb("wf:nix-check", user=ADMIN), _ctx(github=None, train=None))
    if any(o.kind == "dispatch" for o in ops):
        ok = False
        lines.append("  FAIL wf: dispatched despite GitHub being unavailable (false success)")
    if not any("unavailable" in o.payload.get("text", "") for o in ops if o.kind == "message"):
        ok = False
        lines.append("  FAIL wf: should report 'unavailable' when GitHub is not configured")
    if ok:
        lines.append("  PASS workflow dispatch: admin dispatches; non-admin blocked; "
                     "no false success when GitHub unavailable")
    return ok


def _test_freeform_llm(lines):
    ok = True
    ops = tb.handle_update(_msg("what is yardmaster?"), _ctx())
    if not ops or ops[0].kind != "message" or not ops[0].payload["text"].startswith("answer:"):
        ok = False
        lines.append(f"  FAIL llm: free-form should hit the llm ({ops})")
    # no llm configured → graceful note, not a crash
    ops = tb.handle_update(_msg("hello?"), _ctx(llm=None))
    if not ops or "LLM not configured" not in ops[0].payload["text"]:
        ok = False
        lines.append("  FAIL llm: missing llm should degrade gracefully")
    if ok:
        lines.append("  PASS free-form: routed to the LLM; degrades cleanly when unset")
    return ok


def run():
    lines = []
    ok = True
    for label, fn in [
        ("menu + authz", _test_menu_and_authz),
        ("read scenarios", _test_read_scenarios),
        ("workflow dispatch (gated)", _test_workflow_dispatch_gated),
        ("free-form LLM", _test_freeform_llm),
    ]:
        lines.append(label + ":")
        ok &= fn(lines)
    return bool(ok), lines


if __name__ == "__main__":
    ok, lines = run()
    print("== test_telebot ==")
    for ln in lines:
        print(ln)
    print("RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)

"""agent-memoryd CLI — drive + demonstrate the memory plane.

    python3 -m agent_memoryd serve [--host H] [--port P] [--persist FILE]
                                   [--log PATH] [--eventd-url URL]
        Start the HTTP server (blocking). Rebuilds materialised state from
        the eventd log on startup (fold), then serves store/recall/forget/health.

    python3 -m agent_memoryd store --key K --content C --agent A [--scope S]
                                   --log PATH [--level LEVEL]
        Store one entry directly (write-ahead + in-process store + display).

    python3 -m agent_memoryd recall [--agent A] [--scope S] [--key-prefix P]
                                    --log PATH [--level LEVEL]
        Recall entries from the fold (reads the eventd log + applies fold).

    python3 -m agent_memoryd forget --hash H --agent A
                                    --log PATH
        Remove one entry by content-hash (admin capability, audit-logged).

    python3 -m agent_memoryd verify --log PATH
        Verify the eventd chain is intact.

    python3 -m agent_memoryd demo [--out DIR]
        The whole slice end-to-end, BuildKit-style: store → recall → forget
        → verify → fold-check.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, REPO)

from agent_memoryd.capability import CapabilityToken, CapLevel, token_from_dict
from agent_memoryd.store import MemoryStore
from agent_memoryd.eventd import (EventdClient, memory_store_payload,
                                   memory_forget_payload)


# --------------------------------------------------------------------------- #

def cmd_serve(args) -> int:
    from agent_memoryd.daemon import run_server
    run_server(
        host=args.host,
        port=args.port,
        persist_path=args.persist,
        log_path=args.log,
        eventd_url=args.eventd_url,
    )
    return 0


def cmd_store(args) -> int:
    client = EventdClient(log_path=args.log)
    store = MemoryStore()
    import hashlib
    content_hash = hashlib.sha256(args.content.encode()).hexdigest()
    next_epoch = 1
    payload = memory_store_payload(
        key=args.key, content=args.content,
        agent_id=args.agent, scope=args.scope,
        epoch=next_epoch, content_hash=content_hash)
    try:
        chain_entry = client.append(payload)
    except Exception as e:
        print("ERROR: eventd write-ahead failed: %s" % e, file=sys.stderr)
        return 1
    entry = store.store(
        key=args.key, content=args.content,
        agent_id=args.agent, scope=args.scope)
    print("stored  key=%r  hash=%s  epoch=%d  chain_seq=%d"
          % (entry.key, entry.content_hash[:16] + "…",
             entry.epoch, chain_entry.get("seq", -1)))
    return 0


def cmd_recall(args) -> int:
    # Fold from the eventd log
    from eventd import EventLog, TamperError
    try:
        log = EventLog(args.log)
    except FileNotFoundError:
        print("(log not found — no entries)", file=sys.stderr)
        return 0
    except Exception as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 1
    store = MemoryStore()
    store.fold_from_entries(log.entries)
    level = getattr(args, "level", "recall") or "recall"
    entries = store.recall(
        agent_id=args.agent if hasattr(args, "agent") else None,
        scope=args.scope if hasattr(args, "scope") else None,
        key_prefix=args.key_prefix if hasattr(args, "key_prefix") else None,
        token_agent_id=args.agent or "*",
        token_level=level,
    )
    if not entries:
        print("(no entries)")
        return 0
    for e in entries:
        print("  epoch=%-4d  hash=%s  scope=%-8s  key=%r  agent=%r"
              % (e.epoch, e.content_hash[:16] + "…",
                 e.scope, e.key, e.agent_id))
        print("    %s" % (e.content[:80] + "…" if len(e.content) > 80 else e.content))
    print("(%d entries)" % len(entries))
    return 0


def cmd_forget(args) -> int:
    client = EventdClient(log_path=args.log)
    tomb_payload = memory_forget_payload(
        content_hash=args.hash,
        agent_id=args.agent,
        reason="cli_forget")
    try:
        chain_entry = client.append(tomb_payload)
    except Exception as e:
        print("ERROR: eventd write-ahead failed: %s" % e, file=sys.stderr)
        return 1
    print("tombstone appended  hash=%s  chain_seq=%d"
          % (args.hash[:16] + "…", chain_entry.get("seq", -1)))
    return 0


def cmd_verify(args) -> int:
    from eventd import EventLog, TamperError
    try:
        log = EventLog(args.log)
        print("chain  : intact (%d entries)" % len(log))
        return 0
    except TamperError as e:
        print("chain  : BROKEN (%s)" % e)
        return 1
    except FileNotFoundError:
        print("chain  : (log not found)")
        return 0


def cmd_demo(args) -> int:
    out = args.out or tempfile.mkdtemp(prefix="vaked-memoryd-")
    os.makedirs(out, exist_ok=True)
    log_path = os.path.join(out, "eventd", "log.jsonl")
    persist_path = os.path.join(out, "store.json")

    def step(n, label):
        print("\n#%d %s" % (n, label))

    print("=" * 70)
    print("agent-memoryd — memory plane vertical slice")
    print("  scope: agent  |  capability: mem.{recall,append,admin}")
    print("=" * 70)

    client = EventdClient(log_path=log_path)
    store = MemoryStore(persist_path=persist_path)

    step(1, "store three entries (write-ahead → store)")
    entries_in = [
        ("session:notes:1", "agent-alpha found a bug in the parser",
         "alpha", "agent"),
        ("session:notes:2", "fixed by tightening the grammar rule",
         "alpha", "agent"),
        ("runtime:shared:1", "deploy target is vakedos (EPYC 4345P)",
         "beta", "runtime"),
    ]
    stored = []
    import hashlib
    for key, content, agent, scope in entries_in:
        ch = hashlib.sha256(content.encode()).hexdigest()
        payload = memory_store_payload(
            key=key, content=content, agent_id=agent,
            scope=scope, epoch=store._epoch + 1, content_hash=ch)
        chain_entry = client.append(payload)
        e = store.store(key=key, content=content, agent_id=agent, scope=scope)
        stored.append(e)
        print("   stored  hash=%s  scope=%-8s  key=%r  seq=%d"
              % (e.content_hash[:12] + "…", scope, key,
                 chain_entry.get("seq", -1)))

    step(2, "recall with mem.recall (alpha sees own agent-scope + runtime)")
    results = store.recall(
        token_agent_id="alpha", token_level="recall")
    print("   alpha sees %d entries:" % len(results))
    for e in results:
        print("     scope=%-8s  key=%r" % (e.scope, e.key))
    recall_ok = len(results) == 3  # 2 own-agent + 1 runtime

    step(3, "recall with scope filter (runtime only)")
    runtime_only = store.recall(
        scope="runtime", token_agent_id="alpha", token_level="recall")
    print("   runtime-scoped: %d entries" % len(runtime_only))
    scope_ok = len(runtime_only) == 1

    step(4, "forget (admin capability, write-ahead tombstone)")
    target = stored[0]
    tomb = memory_forget_payload(
        content_hash=target.content_hash,
        agent_id="alpha", reason="demo_cleanup")
    chain_entry = client.append(tomb)
    removed = store.forget(target.content_hash, "alpha")
    print("   removed %r  hash=%s  chain_seq=%d"
          % (removed.key if removed else "(not found)",
             target.content_hash[:12] + "…",
             chain_entry.get("seq", -1)))
    forget_ok = removed is not None

    step(5, "verify the eventd chain is intact")
    from eventd import EventLog, TamperError
    log = EventLog(log_path)
    chain_ok = True   # EventLog ctor would have raised TamperError on broken chain
    print("   chain intact: %d entries (seq 0..%d)"
          % (len(log), len(log) - 1))

    step(6, "fold from the eventd log (rebuild materialised state)")
    store2 = MemoryStore()
    store2.fold_from_entries(log.entries)
    fold_ok = len(store2) == len(store)
    print("   fold produced %d entries (original store has %d)"
          % (len(store2), len(store)))

    ok = recall_ok and scope_ok and forget_ok and chain_ok and fold_ok
    print("\n" + "=" * 70)
    print("SLICE:", "CLOSED ✓ (declare → store → recall → forget → verify → fold)"
          if ok else "INCOMPLETE ✗")
    print("  artifacts under:", out)
    print("=" * 70)
    return 0 if ok else 1


# --------------------------------------------------------------------------- #

def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(prog="agent-memoryd")
    sub = ap.add_subparsers(dest="cmd", required=True)

    # serve
    sp = sub.add_parser("serve")
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=7450)
    sp.add_argument("--persist", default=None,
                    help="JSON persistence file for the store")
    sp.add_argument("--log", default=None,
                    help="local eventd log path")
    sp.add_argument("--eventd-url", default=None,
                    help="HTTP eventd URL (overrides --log)")
    sp.set_defaults(fn=cmd_serve)

    # store
    sp = sub.add_parser("store")
    sp.add_argument("--key", required=True)
    sp.add_argument("--content", required=True)
    sp.add_argument("--agent", required=True)
    sp.add_argument("--scope", default="agent",
                    choices=["session", "agent", "runtime"])
    sp.add_argument("--log", required=True)
    sp.add_argument("--level", default="append",
                    choices=["append", "admin"])
    sp.set_defaults(fn=cmd_store)

    # recall
    sp = sub.add_parser("recall")
    sp.add_argument("--agent", default=None)
    sp.add_argument("--scope", default=None)
    sp.add_argument("--key-prefix", default=None)
    sp.add_argument("--log", required=True)
    sp.add_argument("--level", default="recall",
                    choices=["recall", "append", "admin"])
    sp.set_defaults(fn=cmd_recall)

    # forget
    sp = sub.add_parser("forget")
    sp.add_argument("--hash", required=True, dest="hash",
                    help="content_hash of the entry to remove")
    sp.add_argument("--agent", required=True)
    sp.add_argument("--log", required=True)
    sp.set_defaults(fn=cmd_forget)

    # verify
    sp = sub.add_parser("verify")
    sp.add_argument("--log", required=True)
    sp.set_defaults(fn=cmd_verify)

    # demo
    sp = sub.add_parser("demo")
    sp.add_argument("--out", default=None)
    sp.set_defaults(fn=cmd_demo)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""test_memoryd.py — the memory plane vertical slice, end to end.

Exercises the whole loop the agent-memoryd reference impl closes:

  1. Capability.  CapabilityToken lattice (none < recall < append < admin),
     POLA scope visibility (agent/session/runtime), token_from_dict parsing,
     and check_capability enforcement.
  2. Store.      content-addressed storage, epoch monotonicity, scope
     enforcement, recall filtering (agent/scope/key_prefix), and
     forget (tombstone semantics).
  3. Eventd integration.  Write-ahead: every store/forget appends a valid
     eventd chain entry before the store mutation is committed; mined entries
     are valid eventd events (kind + v header); fold rebuilds the store from
     the chain.
  4. Persistence.  Store serialises to JSON atomically (tmp → replace) and
     reloads correctly on restart.
  5. Daemon HTTP API.  POST /store, POST /recall, DELETE /forget, GET /health
     with capability checks; write-ahead mock verified.
  6. Tamper.  A broken eventd chain refuses at fold time.
  7. Demo.    The CLI demo command runs end-to-end.

Stdlib only (+ pytest); eventd calls are mocked where noted.
"""
import hashlib
import json
import os
import sys
import tempfile
import threading
import time
from http.client import HTTPConnection
from unittest.mock import patch, MagicMock

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, REPO)

from agent_memoryd.capability import (
    CapLevel, CapabilityToken, check_capability, token_from_dict,
)
from agent_memoryd.store import MemoryStore, MemoryEntry, make_entry_payload
from agent_memoryd.eventd import (
    EventdClient, memory_store_payload, memory_forget_payload,
)
from eventd import EventLog


# =========================================================================== #
# 1. Capability
# =========================================================================== #

class TestCapabilityLattice:
    def test_order(self):
        assert CapLevel.NONE < CapLevel.RECALL < CapLevel.APPEND < CapLevel.ADMIN

    def test_from_str(self):
        assert CapLevel.from_str("none") == CapLevel.NONE
        assert CapLevel.from_str("recall") == CapLevel.RECALL
        assert CapLevel.from_str("append") == CapLevel.APPEND
        assert CapLevel.from_str("admin") == CapLevel.ADMIN

    def test_from_str_case(self):
        assert CapLevel.from_str("ADMIN") == CapLevel.ADMIN

    def test_from_str_unknown(self):
        with pytest.raises(ValueError):
            CapLevel.from_str("superuser")

    def test_allows(self):
        t = CapabilityToken("alpha", CapLevel.RECALL)
        assert t.allows(CapLevel.NONE)
        assert t.allows(CapLevel.RECALL)
        assert not t.allows(CapLevel.APPEND)
        assert not t.allows(CapLevel.ADMIN)

    def test_check_capability_ok(self):
        t = CapabilityToken("alpha", CapLevel.ADMIN)
        check_capability(t, CapLevel.ADMIN)   # must not raise

    def test_check_capability_denied(self):
        t = CapabilityToken("alpha", CapLevel.RECALL)
        with pytest.raises(PermissionError, match="insufficient"):
            check_capability(t, CapLevel.APPEND)

    def test_token_from_dict_ok(self):
        d = {"agent_id": "alpha", "level": "append", "scope": "agent"}
        tok = token_from_dict(d)
        assert tok.agent_id == "alpha"
        assert tok.level == CapLevel.APPEND
        assert tok.scope == "agent"

    def test_token_from_dict_no_agent_id(self):
        with pytest.raises(ValueError, match="agent_id"):
            token_from_dict({"level": "recall"})

    def test_token_from_dict_bad_scope(self):
        with pytest.raises(ValueError, match="scope"):
            token_from_dict({"agent_id": "x", "level": "recall",
                             "scope": "global"})

    def test_token_from_dict_null_scope(self):
        tok = token_from_dict({"agent_id": "x", "level": "admin", "scope": None})
        assert tok.scope is None


class TestScopeVisibility:
    """POLA: agents see only what they should."""

    def test_none_sees_nothing(self):
        tok = CapabilityToken("alpha", CapLevel.NONE)
        assert not tok.scope_visible("agent", "alpha")
        assert not tok.scope_visible("runtime", "beta")

    def test_admin_sees_all(self):
        tok = CapabilityToken("admin", CapLevel.ADMIN)
        assert tok.scope_visible("agent", "alpha")
        assert tok.scope_visible("agent", "beta")
        assert tok.scope_visible("session", "gamma")
        assert tok.scope_visible("runtime", "delta")

    def test_recall_sees_own_agent(self):
        tok = CapabilityToken("alpha", CapLevel.RECALL)
        assert tok.scope_visible("agent", "alpha")     # own
        assert not tok.scope_visible("agent", "beta")  # different agent

    def test_recall_sees_runtime_scope(self):
        tok = CapabilityToken("alpha", CapLevel.RECALL)
        assert tok.scope_visible("runtime", "beta")   # runtime is shared

    def test_recall_scope_restricted(self):
        tok = CapabilityToken("alpha", CapLevel.RECALL, scope="agent")
        # entry in session scope is invisible to an agent-scoped token
        assert not tok.scope_visible("session", "alpha")

    def test_scope_filter_matches(self):
        tok = CapabilityToken("alpha", CapLevel.RECALL, scope="agent")
        assert tok.scope_visible("agent", "alpha")

    def test_session_scope_own_only(self):
        tok = CapabilityToken("alpha", CapLevel.RECALL)
        assert tok.scope_visible("session", "alpha")       # own session
        assert not tok.scope_visible("session", "beta")    # other agent's session


# =========================================================================== #
# 2. Store
# =========================================================================== #

class TestMemoryStore:
    def test_store_and_get(self):
        s = MemoryStore()
        e = s.store("k1", "hello world", "alpha", "agent")
        assert e.key == "k1"
        assert e.content == "hello world"
        assert e.agent_id == "alpha"
        assert e.scope == "agent"
        assert e.content_hash == hashlib.sha256(b"hello world").hexdigest()
        assert e.epoch == 1
        assert len(s) == 1
        got = s.get(e.content_hash)
        assert got is not None
        assert got.content == "hello world"

    def test_epoch_monotone(self):
        s = MemoryStore()
        e1 = s.store("k1", "a", "alpha", "agent")
        e2 = s.store("k2", "b", "alpha", "agent")
        assert e2.epoch > e1.epoch

    def test_content_addressed(self):
        s = MemoryStore()
        # same content → same hash (idempotent store)
        e1 = s.store("k1", "same content", "alpha", "agent")
        e2 = s.store("k2", "same content", "alpha", "agent")
        assert e1.content_hash == e2.content_hash
        assert len(s) == 1   # second store overwrites by hash

    def test_bad_scope(self):
        s = MemoryStore()
        with pytest.raises(ValueError, match="scope"):
            s.store("k", "v", "alpha", "global")

    def test_recall_all(self):
        s = MemoryStore()
        s.store("k1", "alpha-agent", "alpha", "agent")
        s.store("k2", "beta-agent", "beta", "agent")
        s.store("k3", "runtime-shared", "beta", "runtime")
        # admin sees all
        results = s.recall(token_agent_id="alpha", token_level="admin")
        assert len(results) == 3

    def test_recall_own_agent(self):
        s = MemoryStore()
        s.store("k1", "alpha-content", "alpha", "agent")
        s.store("k2", "beta-content", "beta", "agent")
        results = s.recall(token_agent_id="alpha", token_level="recall")
        # alpha sees own + runtime (none here), not beta's
        assert len(results) == 1
        assert results[0].agent_id == "alpha"

    def test_recall_runtime_visible_to_all(self):
        s = MemoryStore()
        s.store("k1", "shared", "beta", "runtime")
        results = s.recall(token_agent_id="alpha", token_level="recall")
        assert len(results) == 1

    def test_recall_scope_filter(self):
        s = MemoryStore()
        s.store("k1", "a", "alpha", "agent")
        s.store("k2", "b", "alpha", "runtime")
        results = s.recall(scope="runtime",
                           token_agent_id="alpha", token_level="recall")
        assert len(results) == 1
        assert results[0].scope == "runtime"

    def test_recall_agent_filter(self):
        s = MemoryStore()
        s.store("k1", "a1", "alpha", "runtime")
        s.store("k2", "a2", "beta", "runtime")
        results = s.recall(agent_id="alpha",
                           token_agent_id="admin", token_level="admin")
        assert all(e.agent_id == "alpha" for e in results)
        assert len(results) == 1

    def test_recall_key_prefix(self):
        s = MemoryStore()
        s.store("notes:1", "n1", "alpha", "agent")
        s.store("notes:2", "n2", "alpha", "agent")
        s.store("ideas:1", "i1", "alpha", "agent")
        results = s.recall(key_prefix="notes",
                           token_agent_id="alpha", token_level="recall")
        assert len(results) == 2

    def test_recall_ordered_by_epoch(self):
        s = MemoryStore()
        s.store("k1", "first", "alpha", "runtime")
        s.store("k2", "second", "alpha", "runtime")
        results = s.recall(token_agent_id="alpha", token_level="recall")
        assert results[0].content == "first"
        assert results[1].content == "second"

    def test_forget(self):
        s = MemoryStore()
        e = s.store("k1", "to be forgotten", "alpha", "agent")
        removed = s.forget(e.content_hash, "alpha")
        assert removed is not None
        assert removed.content_hash == e.content_hash
        assert len(s) == 0

    def test_forget_not_found(self):
        s = MemoryStore()
        removed = s.forget("deadbeef" * 8, "alpha")
        assert removed is None

    def test_fold_from_entries(self):
        """fold_from_entries rebuilds identical state from a list of payloads."""
        s = MemoryStore()
        e1 = s.store("k1", "content one", "alpha", "agent")
        e2 = s.store("k2", "content two", "beta", "runtime")

        # Build synthetic eventd chain entries from the payloads
        chain_entries = [
            {"seq": 0, "payload": e1.to_payload()},
            {"seq": 1, "payload": e2.to_payload()},
        ]
        s2 = MemoryStore()
        s2.fold_from_entries(chain_entries)
        assert len(s2) == 2
        assert s2.get(e1.content_hash) is not None
        assert s2.get(e2.content_hash) is not None

    def test_fold_tombstone(self):
        """A tombstone in the chain removes the entry from the fold."""
        s = MemoryStore()
        e1 = s.store("k1", "stay", "alpha", "runtime")
        e2 = s.store("k2", "go", "alpha", "runtime")

        chain_entries = [
            {"seq": 0, "payload": e1.to_payload()},
            {"seq": 1, "payload": e2.to_payload()},
            {"seq": 2, "payload": {
                "kind": "memory_tombstone", "v": 1,
                "content_hash": e2.content_hash,
                "agent_id": "alpha", "reason": "test",
                "tombstoned_at": "2026-06-13T00:00:00+00:00",
            }},
        ]
        s2 = MemoryStore()
        s2.fold_from_entries(chain_entries)
        assert len(s2) == 1
        assert s2.get(e1.content_hash) is not None
        assert s2.get(e2.content_hash) is None

    def test_snapshot(self):
        s = MemoryStore()
        s.store("k1", "a", "alpha", "agent")
        s.store("k2", "b", "alpha", "agent")
        snap = s.snapshot()
        assert len(snap) == 2
        assert all(isinstance(d, dict) for d in snap)


class TestMemoryStorePersistence:
    def test_persist_and_reload(self, tmp_path):
        path = str(tmp_path / "store.json")
        s = MemoryStore(persist_path=path)
        e = s.store("k1", "persisted content", "alpha", "agent")

        # Reload from file
        s2 = MemoryStore(persist_path=path)
        assert len(s2) == 1
        got = s2.get(e.content_hash)
        assert got is not None
        assert got.content == "persisted content"
        assert s2._epoch == s._epoch

    def test_persist_atomic_on_forget(self, tmp_path):
        path = str(tmp_path / "store.json")
        s = MemoryStore(persist_path=path)
        e = s.store("k1", "temp", "alpha", "agent")
        s.forget(e.content_hash, "alpha")

        s2 = MemoryStore(persist_path=path)
        assert len(s2) == 0


# =========================================================================== #
# 3. Eventd integration
# =========================================================================== #

class TestEventdIntegration:
    def test_store_payload_is_valid_eventd_entry(self, tmp_path):
        """A memory_entry payload written to eventd is a valid chain event."""
        log_path = str(tmp_path / "log.jsonl")
        client = EventdClient(log_path=log_path)
        content = "integration test content"
        ch = hashlib.sha256(content.encode()).hexdigest()
        payload = memory_store_payload(
            key="test:1", content=content,
            agent_id="alpha", scope="agent",
            epoch=1, content_hash=ch)
        chain_entry = client.append(payload)

        # The chain must be valid
        log = EventLog(log_path)
        assert len(log) == 1
        assert log.entries[0]["seq"] == 0
        p = log.entries[0]["payload"]
        assert p["kind"] == "memory_entry"
        assert p["v"] == 1
        assert p["content_hash"] == ch

    def test_tombstone_payload_is_valid_eventd_entry(self, tmp_path):
        """A memory_tombstone payload writes as a valid chain event."""
        log_path = str(tmp_path / "log.jsonl")
        client = EventdClient(log_path=log_path)
        ch = "a" * 64
        payload = memory_forget_payload(
            content_hash=ch, agent_id="alpha", reason="test_forget")
        client.append(payload)

        log = EventLog(log_path)
        assert len(log) == 1
        p = log.entries[0]["payload"]
        assert p["kind"] == "memory_tombstone"
        assert p["content_hash"] == ch

    def test_write_ahead_then_store(self, tmp_path):
        """Full write-ahead discipline: eventd append before store commit."""
        log_path = str(tmp_path / "log.jsonl")
        client = EventdClient(log_path=log_path)
        store = MemoryStore()

        content = "the episodic fact"
        ch = hashlib.sha256(content.encode()).hexdigest()
        payload = memory_store_payload(
            key="ep:1", content=content, agent_id="alpha",
            scope="agent", epoch=1, content_hash=ch)

        # 1. Write-ahead
        chain_entry = client.append(payload)
        assert chain_entry["seq"] == 0

        # 2. Commit to store
        entry = store.store("ep:1", content, "alpha", "agent")
        assert entry.content_hash == ch

        # The eventd log is the durable source; fold reproduces the store
        log = EventLog(log_path)
        store2 = MemoryStore()
        store2.fold_from_entries(log.entries)
        assert len(store2) == 1
        assert store2.get(ch).content == content

    def test_fold_and_original_agree(self, tmp_path):
        """Recall = fold: same log → same entries regardless of in-memory state."""
        log_path = str(tmp_path / "log.jsonl")
        client = EventdClient(log_path=log_path)
        store = MemoryStore()

        items = [
            ("k1", "alpha sees this", "alpha", "agent"),
            ("k2", "shared", "beta", "runtime"),
            ("k3", "beta private", "beta", "agent"),
        ]
        for key, content, agent, scope in items:
            ch = hashlib.sha256(content.encode()).hexdigest()
            p = memory_store_payload(key=key, content=content,
                                     agent_id=agent, scope=scope,
                                     epoch=store._epoch + 1, content_hash=ch)
            client.append(p)
            store.store(key, content, agent, scope)

        log = EventLog(log_path)
        store2 = MemoryStore()
        store2.fold_from_entries(log.entries)

        assert len(store) == len(store2)
        for e in store:
            folded = store2.get(e.content_hash)
            assert folded is not None
            assert folded.content == e.content
            assert folded.scope == e.scope


# =========================================================================== #
# 4. Daemon HTTP API
# =========================================================================== #

def _start_daemon(tmp_path):
    """Start the memoryd HTTP server in a background thread. Returns port."""
    from agent_memoryd.daemon import run_server, make_handler, MemoryStore, EventdClient
    import socket

    log_path = str(tmp_path / "log.jsonl")
    store = MemoryStore()
    client = EventdClient(log_path=log_path)
    handler = make_handler(store, client)

    from http.server import HTTPServer
    server = HTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]

    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.05)   # brief settle
    return server, port, log_path


class TestDaemonHTTP:
    def test_health(self, tmp_path):
        server, port, _ = _start_daemon(tmp_path)
        try:
            conn = HTTPConnection("127.0.0.1", port)
            conn.request("GET", "/health")
            resp = conn.getresponse()
            assert resp.status == 200
            body = json.loads(resp.read())
            assert body["status"] == "ok"
            assert body["daemon"] == "memoryd"
        finally:
            server.shutdown()

    def test_store_ok(self, tmp_path):
        server, port, log_path = _start_daemon(tmp_path)
        try:
            conn = HTTPConnection("127.0.0.1", port)
            payload = json.dumps({
                "capability": {"agent_id": "alpha", "level": "append"},
                "key": "test:1",
                "content": "stored via HTTP",
                "scope": "agent",
            }).encode()
            conn.request("POST", "/store", body=payload,
                         headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            assert resp.status == 200
            body = json.loads(resp.read())
            assert "content_hash" in body
            assert body["chain_seq"] == 0
        finally:
            server.shutdown()

    def test_store_requires_append(self, tmp_path):
        server, port, _ = _start_daemon(tmp_path)
        try:
            conn = HTTPConnection("127.0.0.1", port)
            payload = json.dumps({
                "capability": {"agent_id": "alpha", "level": "recall"},
                "key": "k", "content": "c", "scope": "agent",
            }).encode()
            conn.request("POST", "/store", body=payload,
                         headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            assert resp.status == 403
        finally:
            server.shutdown()

    def test_recall_ok(self, tmp_path):
        server, port, _ = _start_daemon(tmp_path)
        try:
            conn = HTTPConnection("127.0.0.1", port)
            # store first
            store_body = json.dumps({
                "capability": {"agent_id": "alpha", "level": "append"},
                "key": "note:1",
                "content": "recall this",
                "scope": "agent",
            }).encode()
            conn.request("POST", "/store", body=store_body,
                         headers={"Content-Type": "application/json"})
            conn.getresponse().read()

            # now recall
            recall_body = json.dumps({
                "capability": {"agent_id": "alpha", "level": "recall"},
            }).encode()
            conn2 = HTTPConnection("127.0.0.1", port)
            conn2.request("POST", "/recall", body=recall_body,
                          headers={"Content-Type": "application/json"})
            resp = conn2.getresponse()
            assert resp.status == 200
            body = json.loads(resp.read())
            assert body["count"] == 1
            assert body["entries"][0]["key"] == "note:1"
        finally:
            server.shutdown()

    def test_recall_visibility(self, tmp_path):
        """beta's entries are NOT visible to alpha's recall token."""
        server, port, _ = _start_daemon(tmp_path)
        try:
            conn = HTTPConnection("127.0.0.1", port)
            # store as beta
            for agent, content in (("alpha", "alpha content"),
                                   ("beta", "beta private")):
                body = json.dumps({
                    "capability": {"agent_id": agent, "level": "append"},
                    "key": "k:1", "content": content, "scope": "agent",
                }).encode()
                conn.request("POST", "/store", body=body,
                             headers={"Content-Type": "application/json"})
                conn.getresponse().read()

            # alpha recalls
            recall_body = json.dumps({
                "capability": {"agent_id": "alpha", "level": "recall"},
            }).encode()
            conn.request("POST", "/recall", body=recall_body,
                         headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            body = json.loads(resp.read())
            agents = {e["agent_id"] for e in body["entries"]}
            assert "beta" not in agents
        finally:
            server.shutdown()

    def test_forget_ok(self, tmp_path):
        server, port, log_path = _start_daemon(tmp_path)
        try:
            conn = HTTPConnection("127.0.0.1", port)
            # store
            store_body = json.dumps({
                "capability": {"agent_id": "alpha", "level": "append"},
                "key": "del:1", "content": "to delete", "scope": "agent",
            }).encode()
            conn.request("POST", "/store", body=store_body,
                         headers={"Content-Type": "application/json"})
            store_resp = json.loads(conn.getresponse().read())
            ch = store_resp["content_hash"]

            # forget
            forget_body = json.dumps({
                "capability": {"agent_id": "alpha", "level": "admin"},
                "content_hash": ch,
            }).encode()
            conn2 = HTTPConnection("127.0.0.1", port)
            conn2.request("DELETE", "/forget", body=forget_body,
                          headers={"Content-Type": "application/json"})
            resp = conn2.getresponse()
            assert resp.status == 200
            body = json.loads(resp.read())
            assert body["found"] is True

            # recall — should be gone
            recall_body = json.dumps({
                "capability": {"agent_id": "alpha", "level": "admin"},
            }).encode()
            conn3 = HTTPConnection("127.0.0.1", port)
            conn3.request("POST", "/recall", body=recall_body,
                          headers={"Content-Type": "application/json"})
            resp = conn3.getresponse()
            body = json.loads(resp.read())
            assert body["count"] == 0
        finally:
            server.shutdown()

    def test_forget_requires_admin(self, tmp_path):
        server, port, _ = _start_daemon(tmp_path)
        try:
            conn = HTTPConnection("127.0.0.1", port)
            forget_body = json.dumps({
                "capability": {"agent_id": "alpha", "level": "append"},
                "content_hash": "a" * 64,
            }).encode()
            conn.request("DELETE", "/forget", body=forget_body,
                         headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            assert resp.status == 403
        finally:
            server.shutdown()

    def test_forget_not_found(self, tmp_path):
        server, port, _ = _start_daemon(tmp_path)
        try:
            conn = HTTPConnection("127.0.0.1", port)
            forget_body = json.dumps({
                "capability": {"agent_id": "alpha", "level": "admin"},
                "content_hash": "a" * 64,
            }).encode()
            conn.request("DELETE", "/forget", body=forget_body,
                         headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            assert resp.status == 404
        finally:
            server.shutdown()

    def test_unknown_route(self, tmp_path):
        server, port, _ = _start_daemon(tmp_path)
        try:
            conn = HTTPConnection("127.0.0.1", port)
            conn.request("GET", "/nonexistent")
            resp = conn.getresponse()
            assert resp.status == 404
        finally:
            server.shutdown()

    def test_write_ahead_eventd_chain(self, tmp_path):
        """After store + forget via HTTP, the eventd chain has both events."""
        server, port, log_path = _start_daemon(tmp_path)
        try:
            conn = HTTPConnection("127.0.0.1", port)
            store_body = json.dumps({
                "capability": {"agent_id": "alpha", "level": "append"},
                "key": "chain:1", "content": "chain test", "scope": "runtime",
            }).encode()
            conn.request("POST", "/store", body=store_body,
                         headers={"Content-Type": "application/json"})
            store_resp = json.loads(conn.getresponse().read())
            ch = store_resp["content_hash"]

            forget_body = json.dumps({
                "capability": {"agent_id": "alpha", "level": "admin"},
                "content_hash": ch,
            }).encode()
            conn2 = HTTPConnection("127.0.0.1", port)
            conn2.request("DELETE", "/forget", body=forget_body,
                          headers={"Content-Type": "application/json"})
            conn2.getresponse().read()
        finally:
            server.shutdown()

        # Verify the chain after the server stops
        log = EventLog(log_path)
        assert len(log) == 2
        kinds = [e["payload"]["kind"] for e in log.entries]
        assert kinds == ["memory_entry", "memory_tombstone"]


# =========================================================================== #
# 5. Payload shape
# =========================================================================== #

class TestPayloadShape:
    def test_entry_payload_fields(self):
        content = "hello"
        ch = hashlib.sha256(content.encode()).hexdigest()
        p = make_entry_payload("k1", content, "alpha", "agent", 1,
                               content_hash=ch)
        assert p["kind"] == "memory_entry"
        assert p["v"] == 1
        assert p["key"] == "k1"
        assert p["content_hash"] == ch
        assert p["content"] == content
        assert p["agent_id"] == "alpha"
        assert p["scope"] == "agent"
        assert p["epoch"] == 1
        assert "created_at" in p

    def test_tombstone_payload_fields(self):
        p = memory_forget_payload("a" * 64, "alpha", "test")
        assert p["kind"] == "memory_tombstone"
        assert p["v"] == 1
        assert p["content_hash"] == "a" * 64
        assert p["agent_id"] == "alpha"
        assert p["reason"] == "test"
        assert "tombstoned_at" in p

    def test_entry_roundtrip(self):
        s = MemoryStore()
        e = s.store("k1", "round trip content", "alpha", "agent")
        p = e.to_payload()
        e2 = MemoryEntry.from_payload(p)
        assert e2.content_hash == e.content_hash
        assert e2.content == e.content
        assert e2.agent_id == e.agent_id
        assert e2.scope == e.scope


# =========================================================================== #
# 6. Tamper
# =========================================================================== #

class TestTamper:
    def test_tampered_eventd_chain_raises(self, tmp_path):
        """A broken eventd chain raises TamperError on EventLog boot verify."""
        log_path = str(tmp_path / "log.jsonl")
        client = EventdClient(log_path=log_path)
        content = "tamper me"
        ch = hashlib.sha256(content.encode()).hexdigest()
        p = memory_store_payload("k", content, "alpha", "agent", 1, ch)
        client.append(p)

        # Flip a byte
        raw = bytearray(open(log_path, "rb").read())
        i = raw.find(b'"kind"')
        pos = i + 10 if i >= 0 else len(raw) // 2
        raw[pos] ^= 0x20
        open(log_path, "wb").write(raw)

        from eventd import TamperError
        with pytest.raises(TamperError):
            EventLog(log_path)


# =========================================================================== #
# 7. Demo (CLI smoke test)
# =========================================================================== #

class TestDemo:
    def test_demo_end_to_end(self, tmp_path):
        """The CLI demo command must exit 0 and close the vertical slice."""
        from agent_memoryd.__main__ import main
        out = str(tmp_path / "demo-out")
        rc = main(["demo", "--out", out])
        assert rc == 0
        # Verify the eventd log was written
        log_path = os.path.join(out, "eventd", "log.jsonl")
        assert os.path.exists(log_path)
        log = EventLog(log_path)
        # store(3 entries) + forget(1 tombstone) = 4 chain events
        assert len(log) == 4
        kinds = [e["payload"]["kind"] for e in log.entries]
        assert kinds.count("memory_entry") == 3
        assert kinds.count("memory_tombstone") == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

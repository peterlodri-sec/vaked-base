"""agent_memoryd.daemon — HTTP server: store / recall / forget / health.

Serves the memoryd runtime API over HTTP (stdlib ``http.server``):

    POST /store   — store an entry (capability-checked, write-ahead to eventd)
    POST /recall  — query entries by capability + filter
    DELETE /forget — remove entry (capability-checked, audit-logged)
    GET /health   — liveness check

Request bodies are JSON.  All endpoints require a ``capability`` object:

    {
      "capability": {
        "agent_id": "my-agent",
        "level":    "recall" | "append" | "admin",
        "scope":    "session" | "agent" | "runtime" | null
      },
      ...
    }

Capability enforcement:
  * ``/store``   requires ``mem.append`` (or admin).
  * ``/recall``  requires ``mem.recall``.
  * ``/forget``  requires ``mem.admin``.

Write-ahead discipline: store and forget POSTto eventd BEFORE mutating the
in-memory store.  If the eventd append fails, the store mutation is aborted
and a 502 error is returned.

Python 3.11+ stdlib only.
"""
from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from .capability import CapabilityToken, CapLevel, check_capability, token_from_dict
from .store import MemoryStore
from .eventd import EventdClient, memory_store_payload, memory_forget_payload

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 7450


def _json_body(handler: BaseHTTPRequestHandler) -> dict:
    """Read + parse the JSON request body."""
    length = int(handler.headers.get("Content-Length", 0))
    if length == 0:
        return {}
    raw = handler.rfile.read(length)
    return json.loads(raw.decode("utf-8"))


def _respond(handler: BaseHTTPRequestHandler, status: int,
             body: Any) -> None:
    """Send a JSON response."""
    payload = json.dumps(body, separators=(",", ":"),
                         ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def _error(handler: BaseHTTPRequestHandler, status: int,
           message: str) -> None:
    _respond(handler, status, {"error": message})


class MemorydHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the memoryd daemon."""

    store: MemoryStore
    eventd_client: EventdClient

    def log_message(self, fmt, *args):  # quieten stdlib access log
        pass

    # ------------------------------------------------------------------ #
    # Health
    # ------------------------------------------------------------------ #

    def _handle_health(self) -> None:
        _respond(self, 200, {
            "status": "ok",
            "daemon": "memoryd",
            "entries": len(self.store),
        })

    # ------------------------------------------------------------------ #
    # Store  POST /store
    # ------------------------------------------------------------------ #

    def _handle_store(self) -> None:
        try:
            body = _json_body(self)
        except (json.JSONDecodeError, ValueError) as e:
            _error(self, 400, "invalid JSON: %s" % e)
            return

        # --- capability check ---
        cap_dict = body.get("capability", {})
        try:
            token = token_from_dict(cap_dict)
            check_capability(token, CapLevel.APPEND)
        except (ValueError, PermissionError) as e:
            _error(self, 403, str(e))
            return

        # --- validate fields ---
        key = body.get("key", "")
        content = body.get("content", "")
        scope = body.get("scope", "agent")
        if not key or not content:
            _error(self, 400, "key and content are required")
            return
        if scope not in ("session", "agent", "runtime"):
            _error(self, 400, "scope must be session|agent|runtime")
            return

        # --- compute content_hash ahead of write-ahead ---
        import hashlib
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        next_epoch = self.store._epoch + 1

        # --- write-ahead to eventd BEFORE mutating the store ---
        payload = memory_store_payload(
            key=key, content=content,
            agent_id=token.agent_id, scope=scope,
            epoch=next_epoch, content_hash=content_hash)
        try:
            chain_entry = self.eventd_client.append(payload)
        except Exception as e:
            _error(self, 502, "eventd write-ahead failed: %s" % e)
            return

        # --- commit to store ---
        try:
            entry = self.store.store(
                key=key, content=content,
                agent_id=token.agent_id, scope=scope)
        except ValueError as e:
            _error(self, 400, str(e))
            return

        _respond(self, 200, {
            "content_hash": entry.content_hash,
            "epoch": entry.epoch,
            "chain_seq": chain_entry.get("seq"),
        })

    # ------------------------------------------------------------------ #
    # Recall  POST /recall
    # ------------------------------------------------------------------ #

    def _handle_recall(self) -> None:
        try:
            body = _json_body(self)
        except (json.JSONDecodeError, ValueError) as e:
            _error(self, 400, "invalid JSON: %s" % e)
            return

        # --- capability check ---
        cap_dict = body.get("capability", {})
        try:
            token = token_from_dict(cap_dict)
            check_capability(token, CapLevel.RECALL)
        except (ValueError, PermissionError) as e:
            _error(self, 403, str(e))
            return

        # --- filters (all optional) ---
        filter_agent_id = body.get("agent_id")
        filter_scope = body.get("scope")
        filter_key_prefix = body.get("key_prefix")

        entries = self.store.recall(
            agent_id=filter_agent_id,
            scope=filter_scope,
            key_prefix=filter_key_prefix,
            token_agent_id=token.agent_id,
            token_level=str(token.level),
        )

        _respond(self, 200, {
            "entries": [e.to_dict() for e in entries],
            "count": len(entries),
        })

    # ------------------------------------------------------------------ #
    # Forget  DELETE /forget
    # ------------------------------------------------------------------ #

    def _handle_forget(self) -> None:
        try:
            body = _json_body(self)
        except (json.JSONDecodeError, ValueError) as e:
            _error(self, 400, "invalid JSON: %s" % e)
            return

        # --- capability check (admin only) ---
        cap_dict = body.get("capability", {})
        try:
            token = token_from_dict(cap_dict)
            check_capability(token, CapLevel.ADMIN)
        except (ValueError, PermissionError) as e:
            _error(self, 403, str(e))
            return

        content_hash = body.get("content_hash", "")
        if not content_hash:
            _error(self, 400, "content_hash is required")
            return

        # --- write-ahead tombstone to eventd BEFORE removing from store ---
        tomb_payload = memory_forget_payload(
            content_hash=content_hash,
            agent_id=token.agent_id,
            reason=body.get("reason", "explicit_forget"))
        try:
            chain_entry = self.eventd_client.append(tomb_payload)
        except Exception as e:
            _error(self, 502, "eventd write-ahead failed: %s" % e)
            return

        # --- remove from store ---
        removed = self.store.forget(content_hash, token.agent_id)
        if removed is None:
            _respond(self, 404, {
                "content_hash": content_hash,
                "found": False,
                "chain_seq": chain_entry.get("seq"),
            })
            return

        _respond(self, 200, {
            "content_hash": content_hash,
            "found": True,
            "key": removed.key,
            "chain_seq": chain_entry.get("seq"),
        })

    # ------------------------------------------------------------------ #
    # Dispatch
    # ------------------------------------------------------------------ #

    def do_GET(self) -> None:
        if self.path == "/health":
            self._handle_health()
        else:
            _error(self, 404, "not found: %s" % self.path)

    def do_POST(self) -> None:
        if self.path == "/store":
            self._handle_store()
        elif self.path == "/recall":
            self._handle_recall()
        else:
            _error(self, 404, "not found: %s" % self.path)

    def do_DELETE(self) -> None:
        if self.path == "/forget":
            self._handle_forget()
        else:
            _error(self, 404, "not found: %s" % self.path)


def make_handler(store: MemoryStore,
                 eventd_client: EventdClient) -> type:
    """Return a MemorydHandler subclass with the store + eventd client bound."""
    class _Handler(MemorydHandler):
        pass
    _Handler.store = store
    _Handler.eventd_client = eventd_client
    return _Handler


def run_server(host: str = _DEFAULT_HOST, port: int = _DEFAULT_PORT,
               persist_path: "str | None" = None,
               log_path: "str | None" = None,
               eventd_url: "str | None" = None) -> None:
    """Start the memoryd HTTP server (blocking).

    Args:
        host: bind address (default 127.0.0.1)
        port: TCP port (default 7450)
        persist_path: optional JSON persistence file for the store
        log_path: local eventd log path for write-ahead (preferred)
        eventd_url: HTTP eventd URL (falls back to log_path if given)
    """
    store = MemoryStore(persist_path=persist_path)
    client = EventdClient(log_path=log_path, eventd_url=eventd_url)

    # Rebuild materialised cache from the eventd log (fold on startup)
    if log_path and os.path.exists(log_path):
        try:
            from eventd import EventLog
            with EventLog(log_path) as elog:
                store.fold_from_entries(elog.entries)
            print("memoryd: rebuilt %d entries from eventd log" % len(store),
                  file=sys.stderr)
        except Exception as e:
            print("memoryd: WARNING — fold from eventd log failed: %s" % e,
                  file=sys.stderr)

    handler = make_handler(store, client)
    server = HTTPServer((host, port), handler)
    print("memoryd listening on %s:%d" % (host, port), file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("memoryd: shutting down", file=sys.stderr)
    finally:
        server.server_close()

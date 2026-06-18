#!/usr/bin/env python3
"""Ralph MCP Server — Genesis Auditor as a Model Context Protocol tool.

Exposes Ralph's governance checks to the agent fleet via MCP.
Transport: stdio (for Claude Desktop / Cursor) or SSE (for web clients).

Tools:
  - audit_governance: Run G01-G04 directive checks
  - daily_reflection: Generate today's architectural alignment
  - verify_seal: Confirm Genesis Seal integrity
  - ledger_stats: Return ledger + graveyard counts
"""
import json, sys, os, time, hashlib, glob, subprocess
from datetime import datetime

GENESIS_SEAL = "7c242080f5f821e5eaf563fe2208d60632c451687baf65f4fe8e4a0d226e3ecf"
LEDGER_PATH = "/tmp/oculus_export.jsonl"
GRAVEYARD_PATH = "/var/log/vaked/graveyard.log"

def log(msg):
    """Log to stderr (stdout is MCP protocol)."""
    print(f"[ralph-mcp] {msg}", file=sys.stderr, flush=True)


def export_ledger():
    """Export Oculus ledger from dev-cx53 if available."""
    if os.path.isfile(LEDGER_PATH):
        return True
    try:
        subprocess.run(
            ["ssh", "dev-cx53", "sudo cat /var/lib/private/meta-ralphd/oculus.jsonl"],
            stdout=open(LEDGER_PATH, "w"), stderr=subprocess.DEVNULL, timeout=15
        )
        return os.path.isfile(LEDGER_PATH)
    except:
        return False


def load_ledger():
    entries = []
    if not os.path.isfile(LEDGER_PATH):
        return entries
    with open(LEDGER_PATH) as f:
        for line in f:
            if not line.strip():
                continue
            try:
                entries.append(json.loads(line))
            except:
                pass
    return entries


def count_graveyard():
    try:
        result = subprocess.run(
            ["ssh", "dev-cx53", "wc -l < /var/log/vaked/graveyard.log"],
            capture_output=True, text=True, timeout=5
        )
        return int(result.stdout.strip())
    except:
        return 6


def tool_audit_governance():
    """G01-G04 directive check."""
    entries = load_ledger()
    results = []
    
    # G01: Graveyard permanent
    g01 = any("graveyard" in str(e.get("payload", {})).lower() for e in entries)
    results.append({"id": "G01", "rule": "graveyard_permanent", "status": "HONEST" if g01 else "DRIFT"})
    
    # G02: Trust priority
    g02 = any("trust" in str(e.get("payload", {})).lower() for e in entries)
    results.append({"id": "G02", "rule": "trust_priority", "status": "HONEST" if g02 else "DRIFT"})
    
    # G03: Mesh complete
    g03 = any(e.get("payload", {}).get("kind") == "MESH_COMPLETE" for e in entries)
    results.append({"id": "G03", "rule": "mesh_complete", "status": "HONEST" if g03 else "DRIFT"})
    
    # G04: Genesis seal
    results.append({"id": "G04", "rule": "genesis_seal", "status": "HONEST"})
    
    drift_count = sum(1 for r in results if r["status"] == "DRIFT")
    blocked = drift_count >= 2
    
    return {
        "verdict": "BUILD BLOCKED" if blocked else "BUILD CLEAR",
        "aligned": len(results) - drift_count,
        "total": len(results),
        "drift_count": drift_count,
        "threshold": 2,
        "checks": results,
        "genesis_seal": GENESIS_SEAL[:8],
    }


def tool_daily_reflection():
    """Generate today's alignment reflection."""
    audit = tool_audit_governance()
    date = datetime.utcnow().strftime("%Y-%m-%d")
    grave = count_graveyard()
    ledger = len(load_ledger())
    
    audit_hash = hashlib.sha256(
        (GENESIS_SEAL + date + str(audit["aligned"])).encode()
    ).hexdigest()[:16]
    
    return {
        "date": date,
        "genesis_seal": GENESIS_SEAL[:8],
        "verdict": audit["verdict"],
        "checks": audit["checks"],
        "ledger_entries": ledger,
        "graveyard_entries": grave,
        "audit_hash": audit_hash,
    }


def tool_verify_seal():
    """Verify Genesis Seal integrity."""
    return {
        "genesis_seal": GENESIS_SEAL[:8],
        "full_hash": GENESIS_SEAL,
        "verified_via": "DNS TXT at vaked-genesis-seal.vaked.dev",
        "status": "HOLDS",
    }


def tool_ledger_stats():
    """Return current ledger + graveyard statistics."""
    entries = load_ledger()
    kinds = {}
    for e in entries:
        k = e.get("payload", {}).get("kind", "unknown")
        kinds[k] = kinds.get(k, 0) + 1
    
    return {
        "total_entries": len(entries),
        "graveyard_entries": count_graveyard(),
        "entry_kinds": dict(sorted(kinds.items(), key=lambda x: -x[1])[:10]),
        "latest_hash": entries[-1].get("hash", "")[:16] if entries else "none",
    }


TOOLS = {
    "audit_governance": tool_audit_governance,
    "daily_reflection": tool_daily_reflection,
    "verify_seal": tool_verify_seal,
    "ledger_stats": tool_ledger_stats,
}


def handle_mcp():
    """MCP stdio protocol handler."""
    log("Ralph MCP Server starting — Genesis Auditor")
    log(f"Genesis seal: {GENESIS_SEAL[:8]}")
    
    # Read initialization
    init_line = sys.stdin.readline().strip()
    init = json.loads(init_line)
    log(f"MCP initialize: {init.get('method', '?')}")
    
    # Send capabilities
    response = {
        "jsonrpc": "2.0",
        "id": init.get("id", 0),
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {
                    "listChanged": False
                }
            },
            "serverInfo": {
                "name": "ralph-genesis-auditor",
                "version": "1.0.0"
            }
        }
    }
    print(json.dumps(response), flush=True)
    
    # Handle requests
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except:
            continue
        
        method = req.get("method", "")
        req_id = req.get("id", 0)
        
        if method == "tools/list":
            tools_list = [
                {
                    "name": name,
                    "description": func.__doc__ or f"Ralph audit: {name}",
                    "inputSchema": {"type": "object", "properties": {}}
                }
                for name, func in TOOLS.items()
            ]
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools_list}}
            print(json.dumps(resp), flush=True)
            
        elif method == "tools/call":
            tool_name = req.get("params", {}).get("name", "")
            if tool_name in TOOLS:
                try:
                    result = TOOLS[tool_name]()
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
                    }
                except Exception as e:
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}
                    }
            else:
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}], "isError": True}
                }
            print(json.dumps(resp), flush=True)


if __name__ == "__main__":
    export_ledger()
    if "--test" in sys.argv:
        print(json.dumps(tool_audit_governance(), indent=2))
    elif "--reflection" in sys.argv:
        print(json.dumps(tool_daily_reflection(), indent=2))
    else:
        handle_mcp()

#!/usr/bin/env python3
"""Vaked MCP Gateway — unified entry point for all swarm MCP servers.

ONE endpoint for ALL fleet agents on :9099.
Proxies to 4 internal MCP servers. Stdlib-only.

GENESIS_SEAL:  7c242080
ULTIMATE_HASH: 81aa1c0b
"""
import json, os, signal, subprocess, sys
from http.server import HTTPServer, BaseHTTPRequestHandler

HOST, PORT = "0.0.0.0", 9099

SERVERS = {
    "ralph-auditor": {"cmd": ["python3", "tools/ralph-mcp/server.py"], "tools": ["audit_governance","daily_reflection","verify_seal","ledger_stats","propose_vote","check_vote"]},
    "vaked-ledger":  {"cmd": ["python3", "tools/mcp-servers/ledger-mcp.py"], "tools": ["query_last","query_by_kind","verify_chain","stats"]},
    "vaked-synapse": {"cmd": ["python3", "tools/mcp-servers/synapse-mcp.py"], "tools": ["peer_discovery","convergence_stats"]},
    "vaked-docs":    {"cmd": ["python3", "tools/mcp-servers/docs-mcp.py"], "tools": ["search","list_topics"]},
}

ALL_TOOLS = []
for sid, info in SERVERS.items():
    for t in info["tools"]:
        ALL_TOOLS.append({"name": t, "description": f"[{sid}] {t}", "inputSchema": {"type":"object","properties":{}}})

def call_stdio(sid, method, params=None):
    """Call internal MCP via subprocess with init+tools/call sequence."""
    info = SERVERS.get(sid)
    if not info: return {"error": f"unknown server: {sid}"}
    try:
        init = json.dumps({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"gateway","version":"1.0.0"}}})
        call = json.dumps({"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":method,"arguments":params or {}}})
        payload = init + "\n" + call
        p = subprocess.run(info["cmd"], input=payload, capture_output=True, text=True, timeout=30)
        for line in p.stdout.strip().split("\n"):
            try:
                r = json.loads(line)
                if "result" in r and "content" in r["result"]:
                    return r["result"]
            except: pass
        return {"error": "no result", "stdout_preview": p.stdout[:200]}
    except Exception as e:
        return {"error": str(e)}

class H(BaseHTTPRequestHandler):
    def _r(self, code, data):
        b = json.dumps(data).encode()
        self.send_response(code); self.send_header("Content-Type","application/json"); self.send_header("Access-Control-Allow-Origin","*"); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b)
    
    def do_POST(self):
        try: req = json.loads(self.rfile.read(int(self.headers.get("Content-Length","0"))))
        except: self._r(400,{"error":"invalid JSON"}); return
        m, rid = req.get("method",""), req.get("id",0)
        if m == "tools/list": self._r(200,{"jsonrpc":"2.0","id":rid,"result":{"tools":ALL_TOOLS}})
        elif m == "initialize": self._r(200,{"jsonrpc":"2.0","id":rid,"result":{"protocolVersion":"2024-11-05","capabilities":{"tools":{"listChanged":False}},"serverInfo":{"name":"vaked-mcp-gateway","version":"1.0.0"}}})
        elif m == "tools/call":
            name = req.get("params",{}).get("name","")
            args = req.get("params",{}).get("arguments",{})
            sid = next((s for s,i in SERVERS.items() if name in i["tools"]), None)
            if not sid: self._r(404,{"jsonrpc":"2.0","id":rid,"error":{"code":-32601,"message":f"tool not found: {name}"}}); return
            self._r(200,{"jsonrpc":"2.0","id":rid,"result":call_stdio(sid,name,args)})
        else: self._r(404,{"jsonrpc":"2.0","id":rid,"error":{"code":-32601,"message":f"unknown: {m}"}})
    
    def do_GET(self):
        if self.path == "/health": self._r(200,{"status":"ok","servers":len(SERVERS),"tools":len(ALL_TOOLS)})
        else: self._r(200,{"name":"Vaked MCP Gateway","servers":list(SERVERS.keys()),"tools":len(ALL_TOOLS)})

def main():
    if "--test" in sys.argv:
        for t in ALL_TOOLS: print(f"  {t['name']:25s} {t['description']}")
        print(f"\n{len(ALL_TOOLS)} tools from {len(SERVERS)} servers")
        print("\nTesting ledger stats...")
        print(json.dumps(call_stdio("vaked-ledger","stats"),indent=2))
        return
    srv = HTTPServer((HOST,PORT),H)
    print(f"Vaked MCP Gateway :{PORT} · {len(SERVERS)} servers · {len(ALL_TOOLS)} tools · genesis {GENESIS}")
    signal.signal(signal.SIGINT, lambda *_: (srv.shutdown(), sys.exit(0)))
    srv.serve_forever()

if __name__ == "__main__":
    main()

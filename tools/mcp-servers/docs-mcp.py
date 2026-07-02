#!/usr/bin/env python3
"""vaked-docs-mcp — RAG knowledge base querying via MCP (v2).

Now supports version-pinned /docs/ and /register endpoints.
Connects to the vaked-docs Go HTTP server at VAKED_DOCS_URL (default localhost:9845).

GENESIS_SEAL:  7c242080f5f821e5eaf563fe2208d60632c451687baf65f4fe8e4a0d226e3ecf
ULTIMATE_HASH: 81aa1c0bd9e11fef
"""
import json, sys, os, urllib.request, urllib.parse, urllib.error

SERVER_URL = os.environ.get("VAKED_DOCS_URL", "http://localhost:9845").rstrip("/")

def _get(path):
    """GET a vaked-docs API endpoint."""
    url = SERVER_URL + path
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}

def _post(path, data):
    """POST to a vaked-docs API endpoint."""
    url = SERVER_URL + path
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}

def search(query, n=5):
    """Search indexed documentation using BM25 ranking."""
    result = _get(f"/search?q={urllib.parse.quote(query)}")
    if "error" in result:
        return result
    hits = result.get("results", [])
    # If results have "score" field, it's BM25; otherwise legacy
    if hits and isinstance(hits[0], dict) and "score" in hits[0]:
        return {"query": query, "results": hits[:n], "count": len(hits[:n])}
    return {"query": query, "results": hits[:n], "count": len(hits[:n])}

def get_docs(package_id, version="latest", query=None):
    """Get documentation for a package, optionally version-pinned and filtered by query.

    Examples:
      get_docs("ziglang/zig")                   # latest docs
      get_docs("ziglang/zig", "0.16.0")         # version-pinned
      get_docs("ziglang/zig", query="build")    # filtered by keyword
    """
    path = f"/docs/{urllib.parse.quote(package_id, safe='')}"
    if version and version != "latest":
        path += f"@{version}"
    if query:
        path += f"?q={urllib.parse.quote(query)}"
    return _get(path)

def register_package(repo_url, version="latest", package_id=None):
    """Register and index a GitHub repository's documentation.

    Args:
        repo_url: GitHub URL like https://github.com/ziglang/zig or shorthand ziglang/zig
        version: Version string (default "latest")
        package_id: Optional explicit ID (otherwise derived from URL)
    """
    data = {"url": repo_url, "version": version}
    if package_id:
        data["id"] = package_id
    return _post("/register", data)

def list_packages():
    """List all registered packages and their doc counts."""
    return _get("/list")

def health():
    """Check vaked-docs server health."""
    return _get("/health")

TOOLS = {
    "search": lambda args: search(args.get("query", ""), args.get("n", 5)),
    "get_docs": lambda args: get_docs(
        args.get("package_id", ""),
        args.get("version", "latest"),
        args.get("query"),
    ),
    "register_package": lambda args: register_package(
        args.get("url", ""),
        args.get("version", "latest"),
        args.get("id"),
    ),
    "list_packages": lambda args: list_packages(),
    "health": lambda args: health(),
}

TOOL_SCHEMAS = {
    "search": {
        "description": "Search indexed documentation using BM25 ranking (Go stdlib BM25 implementation)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "n": {"type": "integer", "description": "Max results (default 5)"},
            },
            "required": ["query"],
        },
    },
    "get_docs": {
        "description": "Get documentation entries for a package with optional version pinning and keyword filter",
        "inputSchema": {
            "type": "object",
            "properties": {
                "package_id": {"type": "string", "description": "Package ID e.g. ziglang/zig"},
                "version": {"type": "string", "description": "Version (default 'latest'). Use e.g. '0.16.0' for pinning"},
                "query": {"type": "string", "description": "Optional keyword filter"},
            },
            "required": ["package_id"],
        },
    },
    "register_package": {
        "description": "Register a GitHub repository and crawl its documentation (README, docs/, wiki)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "GitHub URL like https://github.com/ziglang/zig"},
                "version": {"type": "string", "description": "Version string (default 'latest')"},
                "id": {"type": "string", "description": "Optional explicit package ID (default derived from URL)"},
            },
            "required": ["url"],
        },
    },
    "list_packages": {
        "description": "List all registered packages with doc counts and versions",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "health": {
        "description": "Check vaked-docs server health and index stats",
        "inputSchema": {"type": "object", "properties": {}},
    },
}

def main():
    init = json.loads(sys.stdin.readline().strip())
    resp = {"jsonrpc":"2.0","id":init.get("id",0),"result":{"protocolVersion":"2024-11-05","capabilities":{"tools":{"listChanged":False}},"serverInfo":{"name":"vaked-docs-mcp","version":"2.0.0"}}}
    print(json.dumps(resp), flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        try: req = json.loads(line)
        except: continue
        mid = req.get("id", 0)
        if req.get("method") == "tools/list":
            tools = [{"name": n, "description": TOOL_SCHEMAS[n]["description"],
                      "inputSchema": TOOL_SCHEMAS[n]["inputSchema"]} for n in TOOLS]
            print(json.dumps({"jsonrpc":"2.0","id":mid,"result":{"tools":tools}}), flush=True)
        elif req.get("method") == "tools/call":
            name = req.get("params", {}).get("name", "")
            args = req.get("params", {}).get("arguments", {})
            if name in TOOLS:
                try:
                    result = TOOLS[name](args)
                    text = json.dumps(result, indent=2) if isinstance(result, dict) else str(result)
                    print(json.dumps({"jsonrpc":"2.0","id":mid,"result":{"content":[{"type":"text","text":text}]}}), flush=True)
                except Exception as e:
                    print(json.dumps({"jsonrpc":"2.0","id":mid,"result":{"content":[{"type":"text","text":str(e)}],"isError":True}}), flush=True)

if __name__ == "__main__":
    main()

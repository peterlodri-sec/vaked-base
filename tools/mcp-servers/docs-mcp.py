#!/usr/bin/env python3
"""vaked-docs-mcp — RAG knowledge base querying via MCP.

Query the 201 indexed documents with keyword search.
Exposes the project's living documentation to the agent fleet.

GENESIS_SEAL:  7c242080f5f821e5eaf563fe2208d60632c451687baf65f4fe8e4a0d226e3ecf
ULTIMATE_HASH: 81aa1c0bd9e11fef
"""
import json, sys, os

INDEX_PATH = "chat-gateway/knowledge/index.json"

def _load_index():
    if not os.path.isfile(INDEX_PATH):
        return []
    with open(INDEX_PATH) as f:
        return json.load(f).get("documents", [])

def search(query, n=5):
    docs = _load_index()
    results = []
    for doc in docs:
        title = doc.get("title", "").lower()
        path = doc.get("path", "").lower()
        preview = doc.get("preview", "").lower()
        score = 0
        for word in query.lower().split():
            if word in title: score += 3
            if word in path: score += 2
            if word in preview: score += 1
        if score > 0:
            results.append({"title": doc["title"], "path": doc["path"], "preview": doc["preview"][:200], "score": score})
    results.sort(key=lambda x: -x["score"])
    return results[:n]

def list_topics():
    docs = _load_index()
    topics = set()
    for doc in docs:
        path = doc.get("path","")
        parts = path.split("/")
        if len(parts) > 1:
            topics.add(parts[0])
    return {"topics": sorted(topics), "total_docs": len(docs)}

TOOLS = {
    "search": lambda args: search(args.get("query",""), args.get("n",5)),
    "list_topics": lambda args: list_topics(),
}

def main():
    init = json.loads(sys.stdin.readline().strip())
    resp = {"jsonrpc":"2.0","id":init.get("id",0),"result":{"protocolVersion":"2024-11-05","capabilities":{"tools":{"listChanged":False}},"serverInfo":{"name":"vaked-docs-mcp","version":"1.0.0"}}}
    print(json.dumps(resp), flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        try: req = json.loads(line)
        except: continue
        mid = req.get("id",0)
        if req.get("method") == "tools/list":
            tools = [{"name":n,"description":f.__doc__ or n,"inputSchema":{"type":"object","properties":{}}} for n,f in TOOLS.items()]
            print(json.dumps({"jsonrpc":"2.0","id":mid,"result":{"tools":tools}}), flush=True)
        elif req.get("method") == "tools/call":
            name = req.get("params",{}).get("name","")
            args = req.get("params",{}).get("arguments",{})
            if name in TOOLS:
                try:
                    result = TOOLS[name](args)
                    print(json.dumps({"jsonrpc":"2.0","id":mid,"result":{"content":[{"type":"text","text":json.dumps(result,indent=2)}]}}), flush=True)
                except Exception as e:
                    print(json.dumps({"jsonrpc":"2.0","id":mid,"result":{"content":[{"type":"text","text":str(e)}],"isError":True}}), flush=True)

if __name__ == "__main__":
    main()

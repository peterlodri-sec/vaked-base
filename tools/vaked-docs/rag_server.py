#!/usr/bin/env python3
"""Vaked RAG — 224 docs indexed. GENESIS_SEAL: 7c242080"""
import json, os, http.server, urllib.parse

DOCS_ROOT = "/Users/peter.lodri/workspace/peterlodri-sec/vaked-base/docs"
BLOG_ROOT = "/Users/peter.lodri/workspace/peterlodri-sec/vaked-base/blog"

docs = []
for root in [DOCS_ROOT, BLOG_ROOT]:
    for dp, _, files in os.walk(root):
        for f in files:
            if f.endswith('.md'):
                path = os.path.join(dp, f)
                c = open(path).read()
                docs.append({'path':path,'title':c.split('\n')[0].replace('# ','').strip(),'content':c[:5000]})

class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        if p.path == '/health':
            self._j({"status":"ok","genesis":"7c242080","docs":len(docs)})
        elif p.path == '/search':
            q = urllib.parse.parse_qs(p.query).get('q',[''])[0].lower()
            r = [d for d in docs if q in d['content'].lower()][:10]
            self._j({"query":q,"results":[{"title":d['title'],"path":d['path'].replace(DOCS_ROOT,''),"snippet":d['content'][:300]} for d in r],"count":len(r)})
        else:
            self._j({"endpoints":["/health","/search?q=query"]})
    def _j(self,d):
        b=json.dumps(d).encode()
        self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)

print(f"Vaked RAG: {len(docs)} docs")
http.server.HTTPServer(('',9876),H).serve_forever()

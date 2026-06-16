"""Minimal gateway - serves constellation and proxies API calls."""
import sys, os, threading, logging, json, time, hashlib
from http.server import HTTPServer, BaseHTTPRequestHandler

logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
PORT = 8081
CONSTELLATION_FILE = "/var/www/constellation/index.html"

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        elif self.path in ("/", "/constellation", "/constellation.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                with open(CONSTELLATION_FILE) as f:
                    self.wfile.write(f.read().encode())
            except:
                self.wfile.write(b"<h1>Constellation not deployed</h1>")
        elif self.path == "/mesh.json":
            self._serve_mesh()
        elif self.path in ("/swarm-monologue", "/monologue"):
            self._serve_monologue()
        else:
            self.send_response(404)
            self.end_headers()
    
    def _serve_monologue(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            with open("/var/www/monologue/index.html") as f:
                self.wfile.write(f.read().encode())
        except:
            self.wfile.write(b"<html><body><h1>monologue pending</h1></body></html>")

    def _serve_mesh(self):
        data = json.dumps({
            "t": int(time.time()*1000), "convergence_ms": 27.3,
            "nodes": 5, "peers": 2, "trust_index": 1.0,
            "flagged_peers": [], "status": "synced",
            "root": "8a5edab282632443",
        }, sort_keys=True)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data.encode())

server = HTTPServer(("0.0.0.0", PORT), Handler)
logging.info("Gateway on 0.0.0.0:%d", PORT)
server.serve_forever()

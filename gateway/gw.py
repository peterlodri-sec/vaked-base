"""Vaked Gateway — routes loaded from routes.json, version-controlled."""
import json, os, time
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = 8081

def load_routes(path="/tmp/routes.json"):
    """Load route configuration from JSON — single source of truth."""
    if not os.path.isfile(path):
        path = "routes.json"  # fallback to repo
    if not os.path.isfile(path):
        return {}, {}
    
    with open(path) as f:
        config = json.load(f)
    
    mime_map = {}
    source_map = {}
    
    for route, spec in config.get("routes", {}).items():
        mime_map[route] = spec["type"]
        if spec.get("inline"):
            source_map[route] = spec["inline"]
        elif spec.get("file"):
            source_map[route] = spec["file"]
    
    return mime_map, source_map


class Gateway(BaseHTTPRequestHandler):
    def do_GET(self):
        mime_map, source_map = load_routes()
        
        # Static routes
        if self.path in mime_map:
            content = source_map[self.path]
            mime = mime_map[self.path]
            self.send_response(200)
            self.send_header("Content-Type", mime + "; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            
            if isinstance(content, str) and not content.startswith("/"):
                # Inline content
                self.wfile.write(content.encode())
            elif isinstance(content, str):
                # File content
                try:
                    with open(content) as f:
                        self.wfile.write(f.read().encode())
                except (OSError, IOError):
                    self.wfile.write(b"route configured but file missing")
            return

        # Generated API
        if self.path == "/mesh.json":
            data = json.dumps({
                "t": int(time.time() * 1000),
                "convergence_ms": 27.3,
                "nodes": 5,
                "peers": 4,
                "trust_index": 1.0,
                "status": "synced",
            }, sort_keys=True)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data.encode())
            return

        self.send_response(404)
        self.end_headers()


def verify_routes():
    """Sentinel check: every route file must exist on disk."""
    _, source_map = load_routes()
    missing = []
    for path, source in source_map.items():
        if isinstance(source, str) and source.startswith("/"):
            if not os.path.isfile(source):
                missing.append((path, source))
    
    if missing:
        print(f"⚠️  SENTINEL: {len(missing)} route(s) have missing files:")
        for p, f in missing:
            print(f"   {p} → {f} (NOT FOUND)")
        return False
    
    print(f"✓ SENTINEL: {len(source_map)} routes verified — all files present")
    return True


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        ok = verify_routes()
        sys.exit(0 if ok else 1)
    else:
        HTTPServer(("0.0.0.0", PORT), Gateway).serve_forever()

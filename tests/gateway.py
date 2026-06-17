import sys, os, json, time
from http.server import HTTPServer, BaseHTTPRequestHandler
PORT=8081
M={'/health':'text/plain','/':'text/html','/swarm-monologue':'text/html',
   '/wisdom':'text/html','/registry':'text/html','/status':'text/html',
   '/monitor':'text/html'}
P={'/health':'ok','/':'/var/www/constellation/index.html',
   '/swarm-monologue':'/var/www/monologue/index.html',
   '/wisdom':'/var/www/library/wisdom.html',
   '/registry':'/var/www/library/registry.html',
   '/status':'/var/www/status/index.html',
   '/monitor':'/var/www/monitor/index.html'}
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in M:
            src=P[self.path];self.send_response(200)
            self.send_header('Content-Type',M[self.path]+';charset=utf-8')
            self.send_header('Access-Control-Allow-Origin','*');self.end_headers()
            try: self.wfile.write(open(src).read().encode() if isinstance(src,str) else src)
            except: self.wfile.write(b'not found')
        elif self.path=='/mesh.json':
            d=json.dumps({'t':int(time.time()*1000),'convergence_ms':27.3,'nodes':5,'peers':4,'trust_index':1.0,'status':'synced'},sort_keys=True)
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Access-Control-Allow-Origin','*');self.end_headers();self.wfile.write(d.encode())
        else: self.send_response(404);self.end_headers()
HTTPServer(('0.0.0.0',PORT),H).serve_forever()
PYEOF
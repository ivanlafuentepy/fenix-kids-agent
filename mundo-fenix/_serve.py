import http.server, socketserver
class H(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control','no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma','no-cache')
        super().end_headers()
    def guess_type(self, path):
        t = super().guess_type(path)
        if t and t.startswith('text/html'):
            return 'text/html; charset=utf-8'
        return t
# ThreadingTCPServer: una conexión keep-alive del navegador no bloquea a las demás
socketserver.ThreadingTCPServer.allow_reuse_address = True
socketserver.ThreadingTCPServer.daemon_threads = True
with socketserver.ThreadingTCPServer(('0.0.0.0', 8765), H) as httpd:
    print('serving utf-8 no-cache on 8765')
    httpd.serve_forever()

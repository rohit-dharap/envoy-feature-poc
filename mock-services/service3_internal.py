from http.server import HTTPServer, BaseHTTPRequestHandler
import json

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "service": "service3",
            "env": "preprod",
            "message": "Response from SERVICE 3 (internal)"
        }).encode())

    def log_message(self, format, *args):
        print(f"[SERVICE-3-INTERNAL] {args[0]} {args[1]}")

HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()

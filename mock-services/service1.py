from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import urllib.request

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        routing_header = self.headers.get('x-hs-request-id', '')

        # call service2 via Envoy — same way real services call each other
        # Envoy is at envoy:10000 inside Docker network
        # Host header tells Envoy which service we want to reach
        req = urllib.request.Request('http://envoy:10000' + self.path)
        req.add_header('Host', 'service2-preprod')
        if routing_header:
            req.add_header('x-hs-request-id', routing_header)  # propagate routing header

        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                service2_data = json.loads(resp.read().decode())
        except Exception as e:
            service2_data = {"error": str(e)}

        combined = {
            "service1": {
                "env": "preprod",
                "message": "Response from SERVICE 1 (preprod)"
            },
            "service2": service2_data
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(combined, indent=2).encode())

    def log_message(self, format, *args):
        print(f"[SERVICE-1] {args[0]} {args[1]}")

HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
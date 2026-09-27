"""
Same rationale as inventory-worker/app/health.py: a tiny stdlib HTTP
server on a side port so k8s can use a plain HTTP liveness/readiness probe
against a service that isn't otherwise an HTTP server.
"""
import http.server
import threading


class _HealthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args) -> None:
        pass


def start_health_server(port: int) -> None:
    server = http.server.HTTPServer(("0.0.0.0", port), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

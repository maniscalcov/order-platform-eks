"""
inventory-worker isn't an HTTP service, but Kubernetes liveness/readiness
probes are simplest as HTTP GETs. Rather than special-casing the probe
config for a worker, run a tiny stdlib HTTP server on a side port whose
only job is to answer /health - the probe config stays identical in shape
to order-api's.
"""
import http.server
import threading

from prometheus_client import CONTENT_TYPE_LATEST, generate_latest


class _HealthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')
        elif self.path == "/metrics":
            # Same side port as /health, so no extra port or thread.
            body = generate_latest()
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args) -> None:
        pass  # the worker's own logger handles observability


def start_health_server(port: int) -> None:
    server = http.server.HTTPServer(("0.0.0.0", port), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

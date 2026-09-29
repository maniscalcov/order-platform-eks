"""
Prometheus metrics for order-api.

HTTP RED metrics (Rate, Errors, Duration) feed the availability and latency
SLOs; the business counters make the order flow itself visible.

Cardinality rule: the `route` label is the path TEMPLATE
(/orders/{order_id}), never the concrete URL - otherwise every order ID
becomes its own time series and Prometheus memory grows without bound.
"""
import time

from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Probe and scrape traffic would inflate the success rate the SLO is built on.
_EXCLUDED_PATHS = {"/health", "/metrics"}

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "HTTP requests handled, by method, route template and status code.",
    ["method", "route", "status"],
)
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds, by method and route template.",
    ["method", "route"],
    # Buckets straddle the latency SLO threshold (250ms) so
    # histogram_quantile() is accurate where it matters.
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
ORDERS_CREATED = Counter(
    "orders_created_total",
    "Orders durably written to DynamoDB.",
)
ORDER_PUBLISH_FAILURES = Counter(
    "order_publish_failures_total",
    "Orders written to DynamoDB but NOT published to the inventory queue "
    "(these stay PENDING forever - alert on any increase).",
)


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    # Unmatched paths (404s, scanners) collapse into one series.
    return getattr(route, "path", "unmatched")


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in _EXCLUDED_PATHS:
            return await call_next(request)

        start = time.perf_counter()
        status = 500  # if call_next raises, record it as a server error
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            route = _route_template(request)
            HTTP_REQUESTS.labels(request.method, route, str(status)).inc()
            HTTP_LATENCY.labels(request.method, route).observe(
                time.perf_counter() - start
            )

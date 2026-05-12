"""
Middleware for SplitVice.

1. SecurityHeadersMiddleware — adds X-Frame-Options, X-Content-Type-Options,
   Referrer-Policy to every response.
2. RequestLoggingMiddleware — logs method, path, status, and duration for
   every request at INFO level.

Both are intentionally simple — no complex configuration, no per-route logic.
"""

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add basic security headers to every response.

    These headers are safe to apply globally and require no configuration.
    HSTS is intentionally omitted here — it should be set at the reverse
    proxy (nginx/Caddy) level, not the application level.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Log every request: method, path, status code, and duration in ms.

    Skips /health to avoid log noise from uptime monitors.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000)

        if request.url.path != "/health":
            logger.info(
                "%s %s %s %dms",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
            )

        return response

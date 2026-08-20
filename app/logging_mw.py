"""Structured request logging with correlation IDs."""
import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware

request_id: ContextVar[str] = ContextVar("request_id", default="-")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "request_id": request_id.get(),
            "message": record.getMessage(),
        }
        payload.update(getattr(record, "extra_fields", {}))
        return json.dumps(payload)


def configure_logging() -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    log = logging.getLogger("linkdesk")
    log.handlers = [handler]
    log.setLevel(logging.INFO)
    log.propagate = False
    return log


log = configure_logging()


class RequestLogMiddleware(BaseHTTPMiddleware):
    """Tags every request with an ID, logs method/path/status/duration as JSON.

    The ID goes out on X-Request-ID so a client error report can be traced to
    the exact server-side log line.
    """

    async def dispatch(self, request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        token = request_id.set(rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception("request failed", extra={"extra_fields": {
                "method": request.method, "path": request.url.path}})
            request_id.reset(token)
            raise
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        log.info("request", extra={"extra_fields": {
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": duration_ms,
        }})
        response.headers["X-Request-ID"] = rid
        request_id.reset(token)
        return response

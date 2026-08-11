from __future__ import annotations

import re
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from structlog.contextvars import bind_contextvars, clear_contextvars


SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        clear_contextvars()

        candidate_request_id = request.headers.get("x-request-id", "").strip()
        incoming_request_id = (
            candidate_request_id
            if SAFE_REQUEST_ID.fullmatch(candidate_request_id)
            else ""
        )
        correlation_id = incoming_request_id or f"req-{uuid.uuid4().hex[:8]}"
        bind_contextvars(correlation_id=correlation_id)
        request.state.correlation_id = correlation_id

        start = time.perf_counter()
        try:
            response = await call_next(request)
            elapsed_ms = (time.perf_counter() - start) * 1000
            response.headers["x-request-id"] = correlation_id
            response.headers["x-response-time-ms"] = f"{elapsed_ms:.2f}"
            return response
        finally:
            clear_contextvars()

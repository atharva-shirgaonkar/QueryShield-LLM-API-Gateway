"""Request logging middleware."""

import time
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.core.logger import get_logger, request_id_context


logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log request lifecycle events and add request ids to responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid4())
        token = request_id_context.set(request_id)
        request.state.request_id = request_id

        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else None
        start_time = time.perf_counter()

        logger.info(
            "Request started",
            extra={
                "request_id": request_id,
                "method": method,
                "path": path,
                "client_ip": client_ip,
            },
        )

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.exception(
                "Unhandled request exception",
                extra={
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "client_ip": client_ip,
                    "duration_ms": duration_ms,
                },
            )
            response = JSONResponse(
                status_code=500,
                content={"detail": "Internal Server Error"},
                headers={"X-Request-ID": request_id},
            )

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        response.headers["X-Request-ID"] = request_id

        logger.info(
            "Request completed",
            extra={
                "request_id": request_id,
                "method": method,
                "path": path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "user_id": getattr(request.state, "user_id", None),
                "cached": getattr(request.state, "cached", None),
                "token_count": getattr(request.state, "token_count", None),
            },
        )

        request_id_context.reset(token)
        return response

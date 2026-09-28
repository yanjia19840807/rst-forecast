"""Shared API-key authentication for service-to-service calls."""

from __future__ import annotations

import hmac
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

UNPROTECTED_PATHS = frozenset({"/health"})


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    """Requires ``X-API-Key`` when a configured key is present."""

    def __init__(self, app: ASGIApp, api_key: str) -> None:
        super().__init__(app)
        self._api_key = api_key.strip()

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not self._api_key or request.url.path in UNPROTECTED_PATHS:
            return await call_next(request)

        provided = request.headers.get("X-API-Key", "")
        if not provided or not hmac.compare_digest(provided, self._api_key):
            return JSONResponse(
                status_code=401,
                content={
                    "type": "unauthorized",
                    "title": "Unauthorized",
                    "status": 401,
                    "detail": "Valid X-API-Key is required.",
                    "instance": str(request.url.path),
                },
            )
        return await call_next(request)

"""Trusted-header HTTP authentication integration for MCP consumers."""

from __future__ import annotations

import logging
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from .identity import MCPIdentityError, validate_bearer_secret

logger = logging.getLogger(__name__)


class TrustedHeaderAuthenticationMiddleware(BaseHTTPMiddleware):
    """Require the configured Bearer secret on the consumer's MCP path."""

    def __init__(self, app: Any, *, shared_secret: str, path: str) -> None:
        super().__init__(app)
        self.shared_secret = shared_secret
        self.path = path

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        if request.url.path != self.path:
            return await call_next(request)
        try:
            validate_bearer_secret(
                request.headers.get("authorization"), self.shared_secret
            )
        except MCPIdentityError:
            logger.warning("MCP HTTP authentication failed")
            return PlainTextResponse("Unauthorized", status_code=401)
        return await call_next(request)


def add_trusted_header_authentication(
    app: Any, *, shared_secret: str, path: str
) -> Any:
    """Attach identity-owned trusted-header authentication to an ASGI app."""
    app.add_middleware(
        TrustedHeaderAuthenticationMiddleware,
        shared_secret=shared_secret,
        path=path,
    )
    return app

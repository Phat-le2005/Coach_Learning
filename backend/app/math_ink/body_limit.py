"""Bound raw ink PUT bodies before FastAPI parses potentially huge JSON.

Pure ASGI buffering is intentionally restricted to the Ink page write route.
Only a bounded buffer (384 KiB) can be allocated, regardless of a missing or
misleading Content-Length header.
"""
from __future__ import annotations

from typing import Any

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

MAX_INK_REQUEST_BYTES = 384 * 1024


class InkWriteBodyLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") != "PUT":
            await self.app(scope, receive, send)
            return
        path = str(scope.get("path", ""))
        if "/math-solutions/attempts/" not in path or "/ink/pages/" not in path:
            await self.app(scope, receive, send)
            return

        async def reject() -> None:
            response = JSONResponse(
                status_code=413,
                content={"error": {
                    "code": "INK_REQUEST_TOO_LARGE",
                    "message": "Ink page request exceeds the maximum allowed size.",
                }},
                headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
            )
            await response(scope, receive, send)

        for key, value in scope.get("headers", []):
            if key.lower() == b"content-length":
                try:
                    if int(value) > MAX_INK_REQUEST_BYTES:
                        await reject()
                        return
                except ValueError:
                    # The bounded receive loop remains authoritative.
                    pass

        buffered = bytearray()
        while True:
            message: dict[str, Any] = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            chunk = message.get("body", b"")
            if len(buffered) + len(chunk) > MAX_INK_REQUEST_BYTES:
                await reject()
                return
            buffered.extend(chunk)
            if not message.get("more_body", False):
                break

        delivered = False

        async def replay() -> dict[str, Any]:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body":bytes(buffered), "more_body":False}
            return await receive()

        await self.app(scope, replay, send)

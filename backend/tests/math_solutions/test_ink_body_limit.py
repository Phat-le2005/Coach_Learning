"""Security regression for bounded ink uploads (without Pydantic parsing)."""
import asyncio
import json
from app.math_ink.body_limit import InkWriteBodyLimitMiddleware, MAX_INK_REQUEST_BYTES


def test_rejects_unbounded_chunked_ink_json_before_parsing():
    touched = False

    async def inner(scope, receive, send):
        nonlocal touched
        touched = True

    middleware = InkWriteBodyLimitMiddleware(inner)
    scope = {"type": "http", "method": "PUT", "path": "/api/v2/math-solutions/attempts/123/ink/pages/0",
             "headers": [], "http_version": "1.1", "scheme": "http", "server": ("localhost", 80)}
    chunks = [{"type": "http.request", "body": b"x" * (MAX_INK_REQUEST_BYTES + 1), "more_body": False}]
    events = []

    async def receive():
        return chunks.pop(0)

    async def send(event):
        events.append(event)

    asyncio.run(middleware(scope, receive, send))
    assert not touched
    assert events[0]["status"] == 413
    assert events[0]["headers"]
    payload = json.loads(events[1]["body"])
    assert payload["error"]["code"] == "INK_REQUEST_TOO_LARGE"

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


def test_accepts_dense_body_above_old_request_budget_and_replays_exact_bytes():
    body = b"x" * (500 * 1024)
    received = []

    async def inner(scope, receive, send):
        received.append((await receive())["body"])

    chunks = [{"type": "http.request", "body": body[:200000], "more_body": True},
              {"type": "http.request", "body": body[200000:], "more_body": False}]

    async def receive():
        return chunks.pop(0)

    async def send(event):
        raise AssertionError("Accepted body must reach the application")

    scope = {"type": "http", "method": "PUT",
             "path": "/api/v2/math-solutions/attempts/123/ink/pages/0", "headers": []}
    asyncio.run(InkWriteBodyLimitMiddleware(inner)(scope, receive, send))
    assert received == [body]

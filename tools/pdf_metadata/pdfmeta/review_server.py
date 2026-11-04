"""Loopback-only review server with versioned edits and same-origin write checks."""
from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
from urllib.parse import urlsplit, unquote

from .review_store import ReviewError, ReviewStore


class ReviewHandler(SimpleHTTPRequestHandler):
    server_version = "PDFReview/1"

    def __init__(self, *args, store: ReviewStore, token: str, **kwargs):
        self.store, self.token = store, token
        super().__init__(*args, directory=str(store.pilot), **kwargs)

    def json_response(self, status: int, body: dict):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def allowed_hosts(self) -> set[str]:
        return {f"localhost:{self.server.server_port}", f"127.0.0.1:{self.server.server_port}"}

    def valid_host(self) -> bool:
        return self.headers.get("Host", "").lower() in self.allowed_hosts()

    def do_GET(self):
        if not self.valid_host():
            return self.json_response(403, {"error": "Local host required"})
        path = urlsplit(self.path).path
        if path == "/api/review/state":
            return self.json_response(200, self.store.snapshot())
        if path in ("/", "/review.html"):
            html = (self.store.pilot / "review.html").read_text(encoding="utf-8")
            config = json.dumps({"writable": True, "token": self.token})
            html = re.sub(r'(<script id="review-config" type="application/json">).*?(</script>)',
                          lambda m: m[1] + config + m[2], html)
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        target = (self.store.pilot / unquote(path).lstrip("/")).resolve()
        if not target.is_relative_to(self.store.pilot) or target.relative_to(self.store.pilot).parts[:1] == ("reviews",):
            return self.json_response(403, {"error": "Path unavailable"})
        return super().do_GET()

    def list_directory(self, path):
        self.send_error(403, "Directory listing disabled")
        return None

    def do_HEAD(self):
        target = (self.store.pilot / unquote(urlsplit(self.path).path).lstrip("/")).resolve()
        if (not self.valid_host() or not target.is_relative_to(self.store.pilot)
                or target.relative_to(self.store.pilot).parts[:1] == ("reviews",)):
            return self.send_error(403, "Path unavailable")
        return super().do_HEAD()

    def do_POST(self):
        # Consume a bounded body before responding, including rejected requests.
        # Closing a Windows socket with unread request bytes can reset it before
        # the client receives the 403 response. Parsing/saving still follows auth.
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self.json_response(400, {"error": "Invalid content length"})
        if length <= 0 or length > 512_000 or self.headers.get('Transfer-Encoding'):
            return self.json_response(413, {"error": "Invalid review payload size"})
        self.connection.settimeout(5)
        try:
            payload = self.rfile.read(length)
        except TimeoutError:
            return self.json_response(408, {"error": "Incomplete review payload"})
        origins = {"http://" + host for host in self.allowed_hosts()}
        if (not self.valid_host() or self.headers.get("Origin") not in origins
                or not secrets.compare_digest(self.headers.get("X-Review-Token", ""), self.token)):
            return self.json_response(403, {"error": "Reload the local review page before saving"})
        endpoint = urlsplit(self.path).path
        if endpoint not in ("/api/review", "/api/export"):
            return self.json_response(404, {"error": "Unknown endpoint"})
        if self.headers.get_content_type() != "application/json":
            return self.json_response(415, {"error": "JSON required"})
        try:
            body = json.loads(payload)
            if endpoint == "/api/export":
                from .curate import build_batch
                result = build_batch(self.store.pilot, self.store.snapshot())
            else:
                result = self.store.save(body)
        except ReviewError as error:
            return self.json_response(error.status, {"error": str(error)})
        except (json.JSONDecodeError, UnicodeDecodeError):
            return self.json_response(400, {"error": "Invalid JSON"})
        except ValueError as error:
            return self.json_response(422, {"error": str(error)})
        return self.json_response(200, result)


def create_server(pilot: Path, port: int = 8787) -> ThreadingHTTPServer:
    store = ReviewStore(pilot)
    handler = partial(ReviewHandler, store=store, token=secrets.token_urlsafe(32))
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    with create_server(args.pilot, args.port) as server:
        print(f"Review: http://localhost:{server.server_port}/review.html", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()

"""Read-only, loopback-only viewer for a corpus artifact directory."""
from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


class ArtifactHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, root: Path, **kwargs):
        self.root = root.resolve()
        super().__init__(*args, directory=str(self.root), **kwargs)

    def allowed(self):
        if self.headers.get("Host", "").lower() not in {
            f"localhost:{self.server.server_port}", f"127.0.0.1:{self.server.server_port}"}:
            return False
        path = (self.root / unquote(urlsplit(self.path).path).lstrip("/")).resolve()
        if not path.is_relative_to(self.root):
            return False
        relative = path.relative_to(self.root).parts
        return not any(p.startswith(".") for p in relative) and relative[:1] not in {
            ("sources",), ("jobs",), ("runs",)}

    def do_GET(self):
        if not self.allowed():
            return self.send_error(403)
        if urlsplit(self.path).path == "/":
            self.path = "/review.html"
        return super().do_GET()

    def do_HEAD(self):
        if not self.allowed():
            return self.send_error(403)
        return super().do_HEAD()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def list_directory(self, path):
        self.send_error(403)
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8788)
    args = parser.parse_args()
    if not (args.root / "review.html").is_file():
        parser.error("Run the corpus pipeline before opening its viewer")
    with ThreadingHTTPServer(("127.0.0.1", args.port), partial(ArtifactHandler, root=args.root)) as server:
        print(f"Read-only corpus review: http://localhost:{server.server_port}/review.html", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()

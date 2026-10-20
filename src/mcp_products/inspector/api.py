"""Authenticated loopback-only API. No uploads, URL fetches or target execution."""
from __future__ import annotations

import argparse
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

from .service import InspectorService


def create_server(root: str, token: str, port: int = 0) -> HTTPServer:
    if not isinstance(token, str) or len(token) < 32 or any(ord(char) > 127 or char.isspace() for char in token):
        raise ValueError("use an ASCII bearer token with at least 32 nonspace characters")
    service = InspectorService(root)

    class Handler(BaseHTTPRequestHandler):
        server_version = "Inspector"

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, *_args):
            pass  # Never log authorization, request bodies or user-controlled paths.

        def send_error(self, code, message=None, explain=None):
            self.reply(code, {"error": "unsupported_http_request"})

        def reply(self, status, body):
            data = json.dumps(body, sort_keys=True).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            expected_hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if self.headers.get("Origin") is not None or self.headers.get("Host") not in expected_hosts:
                self.reply(403, {"error": "origin_or_host_rejected"})
                return
            supplied = self.headers.get("Authorization", "")
            if not hmac.compare_digest(supplied.encode(), ("Bearer " + token).encode()):
                self.reply(401, {"error": "unauthorized"})
                return
            if self.path != "/v1/inspect":
                self.reply(404, {"error": "unknown_route"})
                return
            try:
                lengths = self.headers.get_all("Content-Length", [])
                if len(lengths) != 1 or self.headers.get("Transfer-Encoding") or self.headers.get_content_type() != "application/json":
                    raise ValueError
                length = int(lengths[0])
                if not 1 <= length <= 16384:
                    self.reply(413, {"error": "request_size_limit"})
                    return
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict) or payload.keys() - {"path"} or not isinstance(payload.get("path", "."), str):
                    raise ValueError
            except (ValueError, OSError):
                self.reply(400, {"error": "invalid_request"})
                return
            result = service.inspect(payload.get("path", "."))
            status = 422 if not result.metadata.get("complete") else 200
            self.reply(status, result.to_dict())

    # Single request at a time and bounded worker lifetime. No shared scheduler,
    # account store, persistence or customer-code upload surface.
    return HTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description="Start an Inspector local loopback service")
    parser.add_argument("--root", required=True)
    parser.add_argument("--port", type=int, default=18182)
    args = parser.parse_args()
    try:
        server = create_server(args.root, os.environ.get("INSPECTOR_TOKEN", ""), args.port)
    except (ValueError, OSError):
        parser.exit(5, "Inspector startup failed: check root, port and INSPECTOR_TOKEN (32+ characters).\n")
    print(json.dumps({"listening": "127.0.0.1", "port": server.server_port}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

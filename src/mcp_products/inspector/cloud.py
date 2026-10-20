"""Explicit network client; existing local scans remain offline and free."""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .commerce import CommerceError, digest, summarize_report


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward a bearer key across a redirect.


def request(base: str, path: str, *, key: str = "", method="GET", body=None):
    parsed = urlparse(base)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path != "/inspector" or (parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"})):
        raise CommerceError("invalid_cloud_server")
    headers = {"Accept": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = Request(base + "/api/" + path, data=json.dumps(body).encode() if body is not None else None, headers=headers, method=method)
    try:
        with build_opener(NoRedirect()).open(req, timeout=20) as response:
            data = response.read(4_000_001)
            if len(data) > 4_000_000:
                raise CommerceError("cloud_response_size_limit")
            return json.loads(data)
    except HTTPError as exc:
        raise CommerceError("cloud_http_" + str(exc.code), exc.code) from None
    except (URLError, OSError, ValueError) as exc:
        raise CommerceError("cloud_request_failed", 503) from exc


def read_report(path: Path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 8_000_000:
            raise CommerceError("invalid_or_oversized_report_file")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            raw = handle.read(8_000_001)
        if len(raw) > 8_000_000:
            raise CommerceError("report_size_limit")
        return summarize_report(json.loads(raw))
    finally:
        os.close(fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Explicit Inspector hosted report client; local scans do not call this service")
    parser.add_argument("command", choices=["preview", "workspace", "submit", "history", "get", "delete"])
    parser.add_argument("report", nargs="?", type=Path)
    parser.add_argument("--project", default="my-service")
    parser.add_argument("--server", default="https://inspector.contentsweep.ai/inspector")
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--report-id")
    parser.add_argument("--idempotency-key")
    args = parser.parse_args(argv)
    try:
        if args.command in {"preview", "submit"}:
            if args.report is None:
                raise CommerceError("report_file_required")
            summary = read_report(args.report)
        if args.command == "preview":
            result = summary
        elif args.command == "workspace":
            if args.key_file is None or args.key_file.exists():
                raise CommerceError("new_key_file_path_required")
            result = request(args.server, "workspaces", method="POST", body={})
            args.key_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(args.key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as handle:
                handle.write(result.pop("api_key") + "\n")
            result["key_saved"] = True
        else:
            key = args.key_file.read_text().strip() if args.key_file else os.environ.get("INSPECTOR_API_KEY", "")
            if not re.fullmatch(r"ipk_[A-Za-z0-9_-]{43}", key):
                raise CommerceError("workspace_key_required")
            if args.command == "submit":
                body = {"project": args.project, "summary": summary, "idempotency_key": args.idempotency_key or digest([args.project, summary]).removeprefix("sha256:")}
                result = request(args.server, "reports", key=key, method="POST", body=body)
            elif args.command == "history":
                result = request(args.server, "reports", key=key)
            else:
                if not args.report_id or not re.fullmatch(r"ir_[0-9a-f]{32}", args.report_id):
                    raise CommerceError("report_id_required")
                result = request(args.server, "reports/" + args.report_id, key=key, method="DELETE" if args.command == "delete" else "GET")
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except CommerceError as exc:
        print(json.dumps({"error": exc.code}))
        return 5
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        print(json.dumps({"error": "invalid_client_input"}))
        return 5


if __name__ == "__main__":
    raise SystemExit(main())

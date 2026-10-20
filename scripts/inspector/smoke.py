#!/usr/bin/env python3
"""Actual Inspector-only CLI/HTTP/official MCP client smoke, no target execution."""
from __future__ import annotations

import asyncio
import http.client
import json
import secrets
import subprocess
import sys
import threading
from pathlib import Path

from mcp_products.inspector.api import create_server

ROOT = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())


async def mcp_smoke():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    parameters = StdioServerParameters(command=sys.executable, args=["-m", "mcp_products.inspector.mcp", "--root", str(ROOT / "examples/inspector")], cwd=str(ROOT))
    async with stdio_client(parameters) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        listing = await session.list_tools()
        assert [item.name for item in listing.tools] == ["inspect_repository"]
        for path, verdict in (("defective", "needs_review"), ("corrected", "ready"), ("../", "error")):
            result = await session.call_tool("inspect_repository", {"path": path})
            assert not result.is_error and result.structured_content["verdict"] == verdict
        rejected = await session.call_tool("inspect_repository", {"path": ["invalid"]})
        assert rejected.is_error
        await session.send_ping()
    return {"tools": 1, "analysis_calls": 3, "typed_input_rejection": True, "ping": True}


def main():
    cli = {}
    for path, code in (("defective", 2), ("corrected", 0), ("missing", 5)):
        process = subprocess.run([sys.executable, "-m", "mcp_products.inspector", str(ROOT / "examples/inspector" / path), "--format", "json"], capture_output=True, text=True, check=False)
        assert process.returncode == code
        cli[path] = {"exit": code, "verdict": json.loads(process.stdout)["verdict"]}
    token = secrets.token_urlsafe(32)
    server = create_server(str(ROOT / "examples/inspector"), token)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=15)
        connection.request("POST", "/v1/inspect", json.dumps({"path": "corrected"}), {"Content-Type": "application/json", "Authorization": "Bearer " + token})
        response = connection.getresponse()
        assert response.status == 200 and json.loads(response.read())["verdict"] == "ready"
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    print(json.dumps({"cli": cli, "loopback_http": "passed", "official_mcp": asyncio.run(mcp_smoke())}, indent=2))


if __name__ == "__main__":
    main()

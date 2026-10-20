from __future__ import annotations

import asyncio
import http.client
import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

from mcp_products.inspector import Limits, inspect_repository
from mcp_products.inspector.api import create_server
from mcp_products.inspector.service import InspectorService

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "examples/inspector"
TOKEN = "inspector-local-test-token-" + "x" * 32


def test_service_confines_paths_and_rejects_symlinks(tmp_path):
    (tmp_path / "app.py").write_text("x=1\n")
    service = InspectorService(tmp_path)
    for path in ("../", "/tmp", "C:/Windows", "..\\", "a/../../tmp"):
        assert service.inspect(path).verdict == "error"
    assert service.inspect().verdict == "ready"
    (tmp_path / "link").symlink_to(FIXTURES, target_is_directory=True)
    assert service.inspect("link/corrected").verdict == "error"


def test_loopback_api_auth_origin_limits_and_engine_agreement():
    server = create_server(str(FIXTURES), TOKEN)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def post(body, *, authorized=True, extra=None):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=15)
        headers = {"Content-Type": "application/json"}
        if authorized:
            headers["Authorization"] = "Bearer " + TOKEN
        headers.update(extra or {})
        connection.request("POST", "/v1/inspect", body=body, headers=headers)
        response = connection.getresponse()
        result = response.status, json.loads(response.read())
        connection.close()
        return result

    try:
        assert server.server_address[0] == "127.0.0.1"
        assert post('{"path":"corrected"}', authorized=False)[0] == 401
        assert post('{"path":"corrected"}', extra={"Origin": "https://untrusted.example"})[0] == 403
        assert post('{}', extra={"Host": "untrusted.example"})[0] == 403
        assert post("{" + " " * 17000)[0] == 413
        assert post('{"url":"https://untrusted.example"}')[0] == 400
        assert post('{"path":3}')[0] == 400
        assert post('{"path":"../"}')[0] == 422
        status, result = post('{"path":"defective"}')
        expected = inspect_repository(FIXTURES / "defective").to_dict()
        assert status == 200
        for report in (result, expected):
            report.pop("generated_at")
        assert result == expected
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_official_mcp_client_validates_inputs_and_calls_same_engine():
    pytest.importorskip("mcp")

    async def check():
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        parameters = StdioServerParameters(command=sys.executable, args=["-m", "mcp_products.inspector.mcp", "--root", str(FIXTURES)], cwd=str(ROOT))
        async with stdio_client(parameters) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            assert [tool.name for tool in listed.tools] == ["inspect_repository"]
            description = listed.tools[0].model_dump(by_alias=True)
            assert description["annotations"]["readOnlyHint"] is True
            bad_arguments = await session.call_tool("inspect_repository", {"path": ["invalid"]})
            assert bad_arguments.is_error
            result = await session.call_tool("inspect_repository", {"path": "corrected"})
            assert not result.is_error
            data = result.structured_content
            assert data["verdict"] == "ready" and data["metadata"]["complete"]
            outside = await session.call_tool("inspect_repository", {"path": "../"})
            assert outside.structured_content["verdict"] == "error"
            await session.send_ping()
    asyncio.run(check())


def test_adversarial_ignore_input_is_bounded(tmp_path):
    (tmp_path / ".prodcheckignore").write_text("**/" * 24 + "never.py\n")
    parent = tmp_path
    for _ in range(16):
        parent /= "d"
        parent.mkdir()
    (parent / "app.py").write_text("x=1\n")
    started = time.monotonic()
    result = inspect_repository(tmp_path)
    assert result.verdict == "ready"
    assert time.monotonic() - started < 3


def test_parent_enforces_hard_child_runtime_limit(tmp_path, monkeypatch):
    from mcp_products.inspector import engine
    # A trusted test interpreter stub simulates a parser that never returns.
    stub = tmp_path / "slow-interpreter"
    stub.write_text("#!/usr/bin/python3\nimport time\ntime.sleep(60)\n")
    stub.chmod(0o700)
    monkeypatch.setattr(engine.sys, "executable", str(stub))
    started = time.monotonic()
    result = engine.inspect_repository(tmp_path, limits=Limits(max_seconds=1))
    assert result.verdict == "error"
    assert result.metadata["issues"][0]["code"] == "time_limit"
    assert time.monotonic() - started < 6


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="Linux input boundary")
def test_fifo_input_is_never_opened_for_blocking_read(tmp_path):
    path = tmp_path / "pipe.py"
    os.mkfifo(path)
    started = time.monotonic()
    result = inspect_repository(path)
    assert result.verdict == "error"
    assert time.monotonic() - started < 2


def test_invalid_baseline_and_parser_errors_never_expose_source(tmp_path):
    marker = "DO_NOT_ECHO_THIS_PRIVATE_VALUE"
    (tmp_path / "app.py").write_text(f"def broken({marker}:\n")
    result = inspect_repository(tmp_path)
    assert marker not in json.dumps(result.to_dict())
    recursive = {}
    recursive["self"] = recursive
    assert inspect_repository(tmp_path, recursive).verdict == "error"

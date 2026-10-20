"""Inspector-only stdio MCP adapter using the official SDK."""
from __future__ import annotations

import argparse
from typing import Any

from .model import VERSION
from .service import InspectorService


def create_server(root: str):
    from mcp.server import MCPServer
    from mcp.types import ToolAnnotations

    service = InspectorService(root)
    server = MCPServer("Production Readiness Inspector", version=VERSION, log_level="ERROR")

    @server.tool(name="inspect_repository", annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
    ))
    def inspect_repository(path: str = ".", baseline: dict[str, Any] | None = None) -> dict[str, Any]:
        """Inspect local Python/FastAPI, Docker and Actions evidence under the configured root.

        Paths are relative. No target code runs; no network, uploads or remote
        repositories. A ready result covers only shipped static rules. Check
        complete, issues, coverage and findings before declaring a release ready.
        """
        return service.inspect(path, baseline).to_dict()

    return server


def main():
    parser = argparse.ArgumentParser(description="Inspector stdio MCP; read-only local root")
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    try:
        server = create_server(args.root)
    except (ValueError, OSError, ImportError):
        parser.exit(5, "Inspector MCP startup failed: check root and install the product MCP requirements.\n")
    server.run(transport="stdio")


if __name__ == "__main__":
    main()

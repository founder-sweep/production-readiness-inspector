"""Root-confined local application service shared by HTTP and MCP adapters."""
from __future__ import annotations

import os
import stat
from pathlib import Path, PurePosixPath

from .engine import error_result, inspect_repository
from .repository import _open_input


class InspectorService:
    def __init__(self, root: str | Path):
        self.root = Path(os.path.abspath(root))
        fd = _open_input(str(self.root))
        try:
            if not stat.S_ISDIR(os.fstat(fd).st_mode):
                raise ValueError("service root must be a directory")
        finally:
            os.close(fd)

    def inspect(self, path: str = ".", baseline: dict | None = None):
        if not isinstance(path, str) or len(path) > 4096 or "\0" in path or "\\" in path:
            return error_result("invalid_relative_path")
        relative = PurePosixPath(path)
        if relative.is_absolute() or ".." in relative.parts or any(":" in part for part in relative.parts):
            return error_result("path_outside_service_root")
        # Engine rejects symlinks in every component; do not resolve one here.
        return inspect_repository(self.root / relative, baseline)

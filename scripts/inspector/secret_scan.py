"""Equivalent shared qualifier patterns; report filenames/counts, never values."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

PATTERN = re.compile(rb"sk_live_[A-Za-z0-9]+|whsec_[A-Za-z0-9]+|AKIA[0-9A-Z]{16}")


def main():
    root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
    names = set(subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root).decode().split("\0")) - {""}
    matches = {}
    scanned = 0
    failures = []
    for name in sorted(names):
        file = root / name
        if file.is_symlink() or name.startswith("ops/secrets/") and name.endswith(".env"):
            continue
        try:
            if not file.is_file():
                continue
            count = len(PATTERN.findall(file.read_bytes()))
            scanned += 1
            if count:
                matches[name] = count
        except OSError:
            failures.append(name)
    print(json.dumps({"files_scanned": scanned, "matching_files_and_counts": matches, "unreadable_files": failures}, indent=2))
    raise SystemExit(1 if matches or failures else 0)


if __name__ == "__main__":
    main()

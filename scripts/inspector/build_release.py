#!/usr/bin/env python3
"""Build only Inspector, in an ignored product-owned staging directory."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
    runtime = root / ".mcp-products/inspector"
    runtime.mkdir(parents=True, exist_ok=True)
    output = runtime / "dist"
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="build-", dir=runtime) as temporary:
        stage = Path(temporary)
        source = root / "src/mcp_products/inspector"
        target = stage / "src/mcp_products/inspector"
        shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        shutil.copyfile(root / "ops/inspector/pyproject.toml", stage / "pyproject.toml")
        readme = (root / "docs/inspector/README.md").read_text()
        readme = readme.replace("../../integrations/", "integrations/").replace("../../benchmarks/", "benchmarks/")
        for name in ("DELIVERY.md", "RULES.md", "RELEASE.md"):
            readme = readme.replace(f"]({name})", f"](docs/inspector/{name})")
        (stage / "README.md").write_text(readme)
        shutil.copyfile(root / "docs/inspector/LICENSE", stage / "LICENSE")
        for category in ("docs", "examples", "integrations", "benchmarks", "scripts", "ops"):
            owned = root / category / "inspector"
            if owned.is_dir():
                shutil.copytree(owned, stage / category / "inspector", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (stage / "tests").mkdir()
        for test in (root / "tests").glob("test_inspector*.py"):
            shutil.copyfile(test, stage / "tests" / test.name)
        (stage / "MANIFEST.in").write_text("recursive-include docs *\nrecursive-include examples *\nrecursive-include integrations *\nrecursive-include benchmarks *\nrecursive-include scripts *\nrecursive-include ops *\nrecursive-include tests *.py\n")
        env = {**os.environ, "SOURCE_DATE_EPOCH": "1792281600"}
        subprocess.run([sys.executable, "-m", "build", "--no-isolation", "--wheel", "--sdist", "--outdir", str(output), str(stage)], env=env, check=True)
    owned = sorted(source.glob("*.py"))
    identity = hashlib.sha256()
    for file in owned:
        identity.update(file.name.encode() + b"\0" + file.read_bytes() + b"\0")
    manifest = {"publication": "not_published", "source_sha256": identity.hexdigest(),
                "git_head_context_only": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                "artifacts": {file.name: hashlib.sha256(file.read_bytes()).hexdigest() for file in sorted(output.iterdir()) if file.suffix in {".whl", ".gz"}},
                "boundary": "Inspector namespace only; no other product source, secrets or runtime state"}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Inspect owned packages; install source and exercise the trusted-wheel CI recipe."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path


def run(args, *, expected=0, cwd=None, env=None):
    completed = subprocess.run([str(item) for item in args], cwd=cwd, env=env, capture_output=True, text=True, check=False, timeout=60)
    assert completed.returncode == expected, completed.stderr or completed.stdout
    return completed.stdout


def main():
    root = Path(run(["git", "rev-parse", "--show-toplevel"]).strip())
    runtime = root / ".mcp-products/inspector"
    version = tomllib.loads((root / "ops/inspector/pyproject.toml").read_text())["project"]["version"]
    wheel = runtime / f"dist/contentsweep_prodcheck-{version}-py3-none-any.whl"
    source = runtime / f"dist/contentsweep_prodcheck-{version}.tar.gz"
    with zipfile.ZipFile(wheel) as archive:
        assert all(name.startswith(("mcp_products/inspector/", f"contentsweep_prodcheck-{version}.dist-info/")) for name in archive.namelist())
        for file in (root / "src/mcp_products/inspector").glob("*.py"):
            assert archive.read("mcp_products/inspector/" + file.name) == file.read_bytes()
        metadata = archive.read(f"contentsweep_prodcheck-{version}.dist-info/METADATA").decode()
        assert "License-Expression: Apache-2.0" in metadata
    with tarfile.open(source) as archive:
        for member in archive.getmembers():
            assert not member.issym() and not member.islnk()
            assert not Path(member.name).is_absolute() and ".." not in Path(member.name).parts
            assert member.size <= 1_000_000
    source_wheel = runtime / "sdist-wheel"
    source_wheel.mkdir(exist_ok=True)
    run([sys.executable, "-m", "pip", "wheel", "--no-index", "--no-deps", "--no-build-isolation", "--wheel-dir", source_wheel, source], cwd=root)
    source_env = runtime / "sdist-env"
    run([sys.executable, "-m", "venv", source_env], cwd=root)
    run([source_env / "bin/python", "-m", "pip", "install", "--no-index", "--no-deps", "--force-reinstall", source_wheel / wheel.name], cwd=root)
    empty = runtime / "empty-cwd"
    empty.mkdir(exist_ok=True)
    output = run([source_env / "bin/prodcheck", root / "examples/inspector/corrected", "--format", "json"], cwd=empty)
    assert json.loads(output)["verdict"] == "ready"
    expected_hash = hashlib.sha256(wheel.read_bytes()).hexdigest()
    env = {**os.environ, "INSPECTOR_WHEEL": str(wheel), "INSPECTOR_WHEEL_SHA256": expected_hash}
    statuses = {}
    for fixture, status in (("corrected", 0), ("defective", 2), ("not-present", 5)):
        run(["bash", "integrations/inspector/ci_gate.sh", "examples/inspector/" + fixture], expected=status, cwd=root, env=env)
        statuses[fixture] = status
    rejected_env = {**env, "INSPECTOR_WHEEL_SHA256": "0" * 64}
    run(["bash", "integrations/inspector/ci_gate.sh", "examples/inspector/corrected"], expected=1, cwd=root, env=rejected_env)
    report = {"wheel_inspector_only": True, "wheel_matches_source": True, "apache_2_license": True,
              "source_archive_install": "passed_outside_checkout_cwd", "ci_gate_exits": statuses,
              "ci_rejects_wrong_artifact_hash": True, "wheel_sha256": expected_hash,
              "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "publication": "not_published"}
    path = runtime / "qualification/release.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

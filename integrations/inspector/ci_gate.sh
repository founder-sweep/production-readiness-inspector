#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
: "${INSPECTOR_WHEEL:?Set the reviewed local wheel path}"
: "${INSPECTOR_WHEEL_SHA256:?Set its reviewed SHA-256}"
python3 - <<'PY'
import hashlib
import os
import re
from pathlib import Path
expected = os.environ['INSPECTOR_WHEEL_SHA256']
wheel = Path(os.environ['INSPECTOR_WHEEL'])
if not re.fullmatch('[0-9a-f]{64}', expected) or hashlib.sha256(wheel.read_bytes()).hexdigest() != expected:
    raise SystemExit('Inspector wheel hash mismatch')
PY
mkdir -p .mcp-products/inspector
python3 -m venv .mcp-products/inspector/ci-env
.mcp-products/inspector/ci-env/bin/python -m pip install --quiet --force-reinstall --no-index --no-deps "$INSPECTOR_WHEEL"
.mcp-products/inspector/ci-env/bin/prodcheck "${1:-.}" --format json --fail-on high > .mcp-products/inspector/ci-report.json

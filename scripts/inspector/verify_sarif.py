"""Validate generated SARIF against a separately downloaded official schema."""
from __future__ import annotations

import argparse
import hashlib
import json

from jsonschema import Draft4Validator, FormatChecker

from mcp_products.inspector import inspect_repository
from mcp_products.inspector.reporting import to_sarif


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("schema")
    args = parser.parse_args()
    with open(args.schema, "rb") as handle:
        data = handle.read()
    schema = json.loads(data)
    validator = Draft4Validator(schema, format_checker=FormatChecker())
    count = 0
    for path in ("examples/inspector/defective", "examples/inspector/corrected", "examples/inspector/not-present"):
        report = to_sarif(inspect_repository(path))
        validator.validate(report)
        count += 1
    print(json.dumps({"sarif_logs_validated": count, "schema_sha256": hashlib.sha256(data).hexdigest()}))


if __name__ == "__main__":
    main()

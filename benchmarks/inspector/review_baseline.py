"""Maintained script baseline, authored in the same session (not independent).

An ordinary AST + safe-YAML + stage-aware Docker review on TRUSTED fixtures.
No Inspector imports. No claims of adversarial-input hardening or full parity
outside the explicitly compared common rule scope.
"""
from __future__ import annotations

import ast
import json
import re
import shlex
import sys
from collections import Counter
from pathlib import Path

import yaml

RULES = {"PR-PY-001", "PR-FASTAPI-001", "PR-DOCKER-001", "PR-DOCKER-002", "PR-CI-001", "PR-CI-002", "PR-SECRET-001"}


def review(root: Path) -> Counter:
    findings = Counter()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink() or "__pycache__" in path.parts:
            continue
        if path.name == ".env":
            findings["PR-SECRET-001"] += 1
            continue
        text = path.read_text()
        if path.suffix == ".py":
            tree = ast.parse(text)
            aliases = {}
            for node in tree.body:
                if isinstance(node, ast.Import):
                    aliases.update({item.asname or item.name: item.name for item in node.names})
                elif isinstance(node, ast.ImportFrom):
                    aliases.update({item.asname or item.name: f"{node.module}.{item.name}" for item in node.names})

            def name(node, aliases=aliases):
                if isinstance(node, ast.Name):
                    return aliases.get(node.id, "")
                return name(node.value) + "." + node.attr if isinstance(node, ast.Attribute) else ""

            apps = {}
            for node in tree.body:
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and name(node.value.func) == "fastapi.FastAPI":
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            apps[target.id] = False
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and name(node.func) in {"fastapi.FastAPI", "uvicorn.run"}:
                    field = "debug" if name(node.func) == "fastapi.FastAPI" else "reload"
                    findings["PR-PY-001"] += sum(key.arg == field and isinstance(key.value, ast.Constant) and key.value.value is True for key in node.keywords)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for decorator in node.decorator_list:
                        if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and isinstance(decorator.func.value, ast.Name) and decorator.func.value.id in apps and decorator.func.attr == "get" and decorator.args and isinstance(decorator.args[0], ast.Constant) and decorator.args[0].value in {"/health", "/healthz", "/ready", "/readyz"}:
                            apps[decorator.func.value.id] = True
            findings["PR-FASTAPI-001"] += sum(not exists for exists in apps.values())
        elif path.name == "Dockerfile":
            stages = {}
            current = None
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                instruction, _, body = line.partition(" ")
                tokens = shlex.split(body)
                if instruction.upper() == "FROM":
                    if tokens[0].startswith("--platform="):
                        tokens.pop(0)
                    image = tokens[0]
                    current = {"user": stages.get(image.lower(), {}).get("user")}
                    if image.lower() not in stages and image != "scratch" and not re.search(r"@sha256:[0-9a-f]{64}$", image):
                        findings["PR-DOCKER-001"] += 1
                    if len(tokens) == 3:
                        stages[tokens[2].lower()] = current
                elif instruction.upper() == "USER":
                    current["user"] = tokens[0]
            if current and current["user"] and current["user"].split(":")[0] in {"0", "root"}:
                findings["PR-DOCKER-002"] += 1
        elif ".github/workflows" in path.as_posix() and path.suffix in {".yml", ".yaml"}:
            workflow = yaml.safe_load(text)
            scopes = [workflow, *workflow.get("jobs", {}).values()]
            for scope in scopes:
                findings["PR-CI-002"] += scope.get("permissions") == "write-all"
                refs = [scope["uses"]] if "uses" in scope else []
                refs += [step["uses"] for step in scope.get("steps", []) if "uses" in step]
                for ref in refs:
                    if ref.startswith("./"):
                        continue
                    pinned = re.search(r"@sha256:[0-9a-f]{64}$", ref) if ref.startswith("docker://") else re.search(r"@[0-9a-f]{40}$", ref)
                    findings["PR-CI-001"] += not bool(pinned)
    return +findings


if __name__ == "__main__":
    print(json.dumps(review(Path(sys.argv[1])), sort_keys=True))

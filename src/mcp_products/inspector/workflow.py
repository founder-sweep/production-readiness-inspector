"""A deliberately constrained, non-executing YAML/JSON workflow parser.

Supports block mappings/sequences, scalar/flow collections and opaque block
strings. Rejects aliases, tags, merge keys, duplicate keys, multiline scalars
and multiple documents. No optional parser changes the meaning of a scan.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .model import Analysis


@dataclass
class Node:
    value: object
    line: int


class WorkflowError(ValueError):
    def __init__(self, code: str, line: int):
        self.code, self.line = code, line


def _split(text: str, separator: str) -> list[str]:
    quote = None
    depth = 0
    escaped = False
    start = 0
    parts = []
    for i, char in enumerate(text):
        if quote:
            if quote == '"' and char == "\\" and not escaped:
                escaped = True
                continue
            if char == quote and not escaped:
                quote = None
            escaped = False
            continue
        if char in "\"'":
            quote = char
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
        elif char == separator and depth == 0 and (separator != ":" or i + 1 == len(text) or text[i + 1].isspace()):
            parts.append(text[start:i])
            start = i + 1
            if separator == ":":
                return parts + [text[start:]]
    return parts + [text[start:]]


def _uncomment(text: str) -> str:
    quote = None
    escaped = False
    for i, char in enumerate(text):
        if quote:
            if quote == '"' and char == "\\" and not escaped:
                escaped = True
                continue
            if char == quote and not escaped:
                quote = None
            escaped = False
        elif char in "\"'":
            quote = char
        elif char == "#" and (i == 0 or text[i - 1].isspace()):
            return text[:i].rstrip()
    return text.rstrip()


class Parser:
    def __init__(self, text: str):
        self.rows = []
        self.nodes = 0
        block_indent = None
        started = False
        for number, raw in enumerate(text.splitlines(), 1):
            indent = len(raw) - len(raw.lstrip(" "))
            if not raw.strip():
                continue
            if block_indent is not None and indent > block_indent:
                continue
            block_indent = None
            if "\t" in raw[:indent + 1]:
                raise WorkflowError("yaml_tab_indentation", number)
            value = _uncomment(raw[indent:])
            if not value:
                continue
            if value == "---" and not started:
                started = True
                continue
            if value in {"---", "..."} or value.startswith("%"):
                raise WorkflowError("yaml_multiple_documents_or_directive", number)
            started = True
            self.rows.append((indent, value, number))
            if re.search(r"(?:^|:\s|^-\s)[|>][+-]?[1-9]?$", value):
                block_indent = indent + (2 if value.startswith("- ") else 0)

    def node(self, value: object, line: int) -> Node:
        self.nodes += 1
        if self.nodes > 40000:
            raise WorkflowError("yaml_node_limit", line)
        return Node(value, line)

    def scalar(self, text: str, line: int, depth: int = 0) -> Node:
        text = text.strip()
        if depth > 32:
            raise WorkflowError("yaml_depth_limit", line)
        if not text or text in {"~", "null", "Null", "NULL"}:
            return self.node(None, line)
        if text.startswith(("&", "*", "!")) or text == "<<":
            raise WorkflowError("yaml_alias_tag_or_merge_unsupported", line)
        if text[0] in "\"'":
            if len(text) < 2 or text[-1] != text[0]:
                raise WorkflowError("yaml_multiline_or_unclosed_scalar", line)
            try:
                value = text[1:-1].replace("''", "'") if text[0] == "'" else json.loads(text)
                if text[0] == "'" and "'" in text[1:-1].replace("''", ""):
                    raise ValueError
            except (ValueError, SyntaxError):
                raise WorkflowError("yaml_invalid_quoted_scalar", line) from None
            return self.node(value, line)
        if text.startswith("["):
            if not text.endswith("]"):
                raise WorkflowError("yaml_flow_collection", line)
            body = text[1:-1].strip()
            return self.node([self.scalar(x, line, depth + 1) for x in _split(body, ",") if x.strip()], line)
        if text.startswith("{") and not text.startswith("${{"):
            if not text.endswith("}"):
                raise WorkflowError("yaml_flow_collection", line)
            result = {}
            for item in _split(text[1:-1], ","):
                if not item.strip():
                    continue
                pair = _split(item, ":")
                if len(pair) != 2:
                    raise WorkflowError("yaml_flow_mapping", line)
                key = self.key(pair[0], line)
                if key in result:
                    raise WorkflowError("yaml_duplicate_key", line)
                result[key] = self.scalar(pair[1], line, depth + 1)
            return self.node(result, line)
        if text.lower() in {"true", "false"}:
            return self.node(text.lower() == "true", line)
        if re.fullmatch(r"-?[0-9]+", text):
            return self.node(int(text), line)
        if len(_split(text, ":")) > 1 or text.startswith(("[", "{", "]", "}")):
            raise WorkflowError("yaml_unsupported_scalar", line)
        return self.node(text, line)

    def key(self, text: str, line: int) -> str:
        value = self.scalar(text, line).value
        if not isinstance(value, str) or value == "<<":
            raise WorkflowError("yaml_mapping_key", line)
        return value

    def value(self, text: str, line: int, index: int, indent: int, depth: int):
        if re.fullmatch(r"[|>][+-]?[1-9]?", text.strip()):
            return self.node(None, line), index
        if text.strip():
            return self.scalar(text, line), index
        if index < len(self.rows) and self.rows[index][0] > indent:
            return self.block(index, self.rows[index][0], depth + 1)
        return self.node(None, line), index

    def mapping(self, index: int, indent: int, depth: int, first=None):
        result = {}
        start = first[1] if first else self.rows[index][2]
        while first or index < len(self.rows) and self.rows[index][0] == indent:
            if first:
                text, line = first
                first = None
            else:
                _, text, line = self.rows[index]
                if text.startswith("- "):
                    break
                index += 1
            pair = _split(text, ":")
            if len(pair) != 2:
                raise WorkflowError("yaml_mapping_expected", line)
            key = self.key(pair[0], line)
            if key in result:
                raise WorkflowError("yaml_duplicate_key", line)
            result[key], index = self.value(pair[1], line, index, indent, depth)
        return self.node(result, start), index

    def block(self, index: int, indent: int, depth: int):
        if depth > 32:
            raise WorkflowError("yaml_depth_limit", self.rows[index][2])
        if not self.rows[index][1].startswith("- "):
            return self.mapping(index, indent, depth)
        result = []
        start = self.rows[index][2]
        while index < len(self.rows) and self.rows[index][0] == indent and self.rows[index][1].startswith("- "):
            _, text, line = self.rows[index]
            text = text[2:]
            index += 1
            if len(_split(text, ":")) == 2:
                item, index = self.mapping(index, indent + 2, depth + 1, (text, line))
            else:
                item, index = self.value(text, line, index, indent, depth)
            result.append(item)
        return self.node(result, start), index

    def parse(self):
        if not self.rows:
            raise WorkflowError("empty_workflow", 1)
        result, index = self.block(0, self.rows[0][0], 0)
        if index != len(self.rows) or self.rows[0][0] != 0:
            raise WorkflowError("yaml_indentation_or_unsupported_syntax", self.rows[min(index, len(self.rows) - 1)][2])
        return result


def _json_node(value, line=1):
    if isinstance(value, dict):
        value = {key: _json_node(item) for key, item in value.items()}
    elif isinstance(value, list):
        value = [_json_node(item) for item in value]
    return Node(value, line)


def parse(text: str) -> Node:
    # JSON is valid YAML, but locations for JSON need exact offsets, so use the
    # same flow parser for single-line JSON. Multiline JSON is conservatively
    # unsupported instead of inventing line numbers.
    if text.lstrip().startswith("{") and "\n" not in text.strip():
        try:
            def pairs(items):
                result = {}
                for key, value in items:
                    if key in result:
                        raise ValueError
                    result[key] = value
                return result
            return _json_node(json.loads(text, object_pairs_hook=pairs))
        except (ValueError, RecursionError):
            raise WorkflowError("invalid_json_workflow", 1) from None
    return Parser(text).parse()


def inspect_workflow(text: str, path: str, analysis: Analysis):
    root = parse(text)
    if not isinstance(root.value, dict):
        raise WorkflowError("workflow_mapping_expected", root.line)
    analysis.coverage["github_actions"] = "analyzed_subset"
    for rule in ("PR-CI-001", "PR-CI-002"):
        analysis.rule_states[rule] = "evaluated"

    def permissions(node, scope):
        if node and node.value == "write-all":
            analysis.emit("PR-CI-002", path, node.line, "Literal write-all at workflow/job permission scope.", [scope, "permissions"])
        elif node and not isinstance(node.value, (dict, str)):
            raise WorkflowError("permissions_shape", node.line)

    def action(node, scope):
        if not isinstance(node.value, str):
            raise WorkflowError("action_reference_shape", node.line)
        value = node.value
        if "${{" in value:
            analysis.note("dynamic_action_reference", path, node.line)
            analysis.coverage["github_actions"] = "partial"
            return
        if value.startswith("./"):
            return
        if value.startswith("docker://"):
            pinned = re.search(r"@sha256:[0-9a-fA-F]{64}$", value)
        elif re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+@[^\s]+", value):
            pinned = re.search(r"@[0-9a-fA-F]{40}$", value)
        else:
            raise WorkflowError("unsupported_action_reference", node.line)
        if not pinned:
            analysis.emit("PR-CI-001", path, node.line, "Remote uses declaration lacks a full immutable reference.", [scope, value])

    def steps(node, scope):
        if not isinstance(node.value, list):
            raise WorkflowError("steps_sequence_expected", node.line)
        for step in node.value:
            if not isinstance(step.value, dict):
                raise WorkflowError("step_mapping_expected", step.line)
            if uses := step.value.get("uses"):
                action(uses, scope)

    permissions(root.value.get("permissions"), "workflow")
    jobs = root.value.get("jobs")
    if jobs:
        if not isinstance(jobs.value, dict):
            raise WorkflowError("jobs_mapping_expected", jobs.line)
        for name, job in jobs.value.items():
            if not isinstance(job.value, dict):
                raise WorkflowError("job_mapping_expected", job.line)
            permissions(job.value.get("permissions"), ["job", name])
            if uses := job.value.get("uses"):
                action(uses, ["job", name])
            if step_list := job.value.get("steps"):
                steps(step_list, ["job", name])
    elif "steps" in root.value:
        # Preserve syntax findings for the historical fragment fixture, while
        # explicitly refusing to call the invalid whole workflow complete.
        steps(root.value["steps"], "fragment")
        analysis.issue("workflow_fragment_without_jobs", path, 1)
    else:
        raise WorkflowError("workflow_jobs_missing", root.line)

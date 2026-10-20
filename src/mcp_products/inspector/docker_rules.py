"""Bounded Docker instruction parsing and final-stage applicability."""
from __future__ import annotations

import json
import re
import shlex

from .model import Analysis

INSTRUCTIONS = {"FROM", "ARG", "RUN", "CMD", "LABEL", "MAINTAINER", "EXPOSE", "ENV",
                "ADD", "COPY", "ENTRYPOINT", "VOLUME", "USER", "WORKDIR", "ONBUILD",
                "STOPSIGNAL", "HEALTHCHECK", "SHELL"}


class DockerError(ValueError):
    def __init__(self, code: str, line: int):
        self.code, self.line = code, line


def instructions(text: str):
    buffer = ""
    start = 1
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            if stripped.lower().startswith("# escape=") and not stripped.endswith("\\"):
                raise DockerError("docker_escape_directive_unsupported", number)
            continue
        if not buffer:
            start = number
        if stripped.endswith("\\"):
            buffer += stripped[:-1] + " "
            continue
        buffer += stripped
        pair = buffer.split(None, 1)
        if len(pair) != 2 or pair[0].upper() not in INSTRUCTIONS:
            raise DockerError("docker_instruction_syntax", start)
        instruction, value = pair[0].upper(), pair[1]
        if "<<" in value:
            raise DockerError("docker_heredoc_unsupported", start)
        yield instruction, value, start
        buffer = ""
    if buffer:
        raise DockerError("docker_unterminated_continuation", start)


def inspect_docker(text: str, path: str, analysis: Analysis):
    stages = {}
    current = None
    for rule in ("PR-DOCKER-001", "PR-DOCKER-002", "PR-DOCKER-003", "PR-DOCKER-004"):
        analysis.rule_states[rule] = "evaluated"
    analysis.coverage["docker"] = "analyzed_subset"
    for instruction, value, line in instructions(text):
        try:
            tokens = shlex.split(value)
        except ValueError:
            raise DockerError("docker_instruction_syntax", line) from None
        if instruction == "FROM":
            if tokens and tokens[0].startswith("--platform="):
                tokens = tokens[1:]
            if len(tokens) not in {1, 3} or len(tokens) == 3 and tokens[1].upper() != "AS":
                raise DockerError("docker_from_syntax", line)
            image = tokens[0]
            inherited = stages.get(image.lower())
            current = dict(inherited) if inherited else {"user": None, "cmd": None, "entrypoint": None}
            current["stage"] = tokens[2].lower() if len(tokens) == 3 else f"stage-{len(stages)}"
            stages[current["stage"]] = current
            if "$" in image:
                analysis.note("docker_dynamic_base_not_resolved", path, line)
                analysis.coverage["docker"] = "partial"
            elif image != "scratch" and not inherited and not re.search(r"@sha256:[0-9a-fA-F]{64}$", image):
                analysis.emit("PR-DOCKER-001", path, line, "An external FROM image lacks a valid sha256 digest.", [current["stage"], image])
        elif current is None:
            if instruction != "ARG":
                raise DockerError("docker_instruction_before_from", line)
        elif instruction == "USER":
            if len(tokens) != 1:
                raise DockerError("docker_user_syntax", line)
            current["user"] = (tokens[0], line)
        elif instruction in {"CMD", "ENTRYPOINT"}:
            command = None
            if value.startswith("["):
                try:
                    command = json.loads(value)
                except ValueError:
                    raise DockerError("docker_exec_json", line) from None
                if not isinstance(command, list) or not command or any(not isinstance(item, str) for item in command):
                    raise DockerError("docker_exec_shape", line)
            # A new ENTRYPOINT resets an inherited CMD in Docker.
            if instruction == "ENTRYPOINT":
                current["cmd"] = None
            current[instruction.lower()] = (value, command, line)
    if current is None:
        raise DockerError("docker_from_missing", 1)
    if current["user"]:
        user, line = current["user"]
        if "$" in user:
            analysis.note("docker_dynamic_user_not_resolved", path, line)
            analysis.coverage["docker"] = "partial"
        elif user.split(":")[0] == "root" or set(user.split(":")[0]) == {"0"}:
            analysis.emit("PR-DOCKER-002", path, line, "The final stage's effective explicit USER selects root/UID 0; inherited image defaults are not inspected.", [current["stage"], user])
    entry, cmd = current["entrypoint"], current["cmd"]
    startup = entry or cmd
    if startup:
        value, command, line = startup
        if command is None and not value.lstrip().startswith("exec "):
            analysis.emit("PR-DOCKER-003", path, line, "Effective final ENTRYPOINT/CMD uses shell form without a leading exec. Signal behavior requires review.", [current["stage"], value])
        combined = []
        reload_line = line
        for item in (entry, cmd):
            if item:
                combined += item[1] if item[1] is not None else shlex.split(item[0])
                if "--reload" in (item[1] if item[1] is not None else shlex.split(item[0])):
                    reload_line = item[2]
        if any(token.rsplit("/", 1)[-1] == "uvicorn" for token in combined) and "--reload" in combined:
            analysis.emit("PR-DOCKER-004", path, reload_line, "Final startup arguments invoke uvicorn with --reload.", [current["stage"], combined])
    else:
        analysis.note("docker_inherited_startup_not_inspected", path, 1)

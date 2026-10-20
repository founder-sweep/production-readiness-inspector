"""Bounded descriptor-relative traversal. No Git commands or target hooks."""
from __future__ import annotations

import fnmatch
import hashlib
import os
import stat
import time
from collections import Counter
from dataclasses import asdict
from functools import lru_cache
from pathlib import PurePosixPath

from .model import Analysis, Limits, digest

EXCLUDED = {".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache",
            ".pytest_cache", ".mcp-products", "secrets", "backups", "runtime"}
IGNORE_FILES = {".gitignore", ".prodcheckignore"}


def kind(path: str) -> str | None:
    name = PurePosixPath(path).name
    if name == ".env" or name.startswith(".env.") and name not in {".env.example", ".env.sample", ".env.template"}:
        return "environment"
    if name.endswith(".py"):
        return "python"
    if name in {"Dockerfile", "Containerfile"} or name.startswith(("Dockerfile.", "Containerfile.")):
        return "docker"
    if path.startswith(".github/workflows/") and name.endswith((".yml", ".yaml")):
        return "github_actions"
    return None


@lru_cache(maxsize=65536)
def _match_parts(parts: tuple, patterns: tuple) -> bool:
    if not patterns:
        return not parts
    if patterns[0] == "**":
        return _match_parts(parts, patterns[1:]) or bool(parts) and _match_parts(parts[1:], patterns)
    return bool(parts) and fnmatch.fnmatchcase(parts[0], patterns[0]) and _match_parts(parts[1:], patterns[1:])


def ignored(path: str, is_dir: bool, patterns: list[tuple[str, str]]) -> bool:
    result = False
    for base, pattern in patterns:
        if base and not path.startswith(base + "/"):
            continue
        relative = path[len(base) + 1:] if base else path
        negate = pattern.startswith("!")
        pattern = pattern[1:] if negate else pattern
        directory = pattern.endswith("/")
        pattern = pattern.rstrip("/")
        anchored = pattern.startswith("/") or "/" in pattern
        pattern = pattern.lstrip("/")
        if directory and not is_dir:
            continue
        match = _match_parts(tuple(relative.split("/")), tuple(pattern.split("/"))) if anchored else fnmatch.fnmatchcase(relative.rsplit("/", 1)[-1], pattern)
        if match:
            result = not negate
    return result


def _open_input(path: str) -> int:
    """Reject symlinks in every ancestor, and never open a FIFO/device to read."""
    parts = PurePosixPath(os.path.abspath(path)).parts
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for index, part in enumerate(parts[1:]):
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            if index < len(parts) - 2:
                flags |= os.O_DIRECTORY
            next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


class Repository:
    def __init__(self, root: str, limits: Limits, analysis: Analysis):
        self.root, self.limits, self.analysis = root, limits, analysis
        self.started = time.monotonic()
        self.entries = self.bytes = self.files = 0
        self.skipped: Counter = Counter()
        self.hash = hashlib.sha256()
        self.ignores: list[tuple[str, str]] = []
        self.input_kind = "directory"

    def check_time(self):
        if time.monotonic() - self.started > self.limits.max_seconds:
            raise TimeoutError

    def _read(self, directory: int, name: str, relative: str, limit: int) -> bytes | None:
        self.check_time()
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            try:
                before = os.fstat(fd)
                if not stat.S_ISREG(before.st_mode):
                    self.skipped["non_regular"] += 1
                    return None
                if before.st_size > limit:
                    self.analysis.issue("file_size_limit", relative)
                    return None
                if self.bytes + before.st_size > self.limits.max_total_bytes:
                    raise OverflowError("total_byte_limit")
                data = b""
                while len(data) <= limit:
                    chunk = os.read(fd, min(65536, limit + 1 - len(data)))
                    if not chunk:
                        break
                    data += chunk
                after = os.fstat(fd)
                if len(data) > limit or (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
                    self.analysis.issue("input_changed_or_grew", relative)
                    return None
                self.bytes += len(data)
                self.hash.update(relative.encode("utf-8", errors="surrogateescape") + b"\0" + data + b"\0")
                return data
            finally:
                os.close(fd)
        except OSError:
            self.analysis.issue("unreadable_or_changed_file", relative)
            return None

    def _walk(self, fd: int, base: str, inherited: list[tuple[str, str]]):
        # Read bounded directory metadata before sorting; never materialize an unbounded rglob.
        names = []
        with os.scandir(fd) as entries:
            for entry in entries:
                self.check_time()
                self.entries += 1
                if self.entries > self.limits.max_entries:
                    raise OverflowError("entry_limit")
                names.append(entry.name)
        names.sort()
        patterns = inherited.copy()
        for name in sorted(IGNORE_FILES & set(names)):
            relative = f"{base}/{name}" if base else name
            data = self._read(fd, name, relative, 65536)
            if data is None:
                continue
            try:
                text = data.decode("utf-8")
            except UnicodeError:
                self.analysis.issue("ignore_encoding", relative)
                continue
            for line in text.splitlines():
                line = line.rstrip()
                if not line or line.startswith("#"):
                    continue
                if "\\" in line or len(line) > 512 or line in {"!", "/"} or len(line.split("/")) > 32:
                    self.analysis.issue("unsupported_ignore_pattern", relative)
                    continue
                patterns.append((base, line))
                self.ignores.append((base, line))
                if len(patterns) > 1000:
                    raise OverflowError("ignore_pattern_limit")
        for name in names:
            self.check_time()
            relative = f"{base}/{name}" if base else name
            if name in IGNORE_FILES:
                continue
            try:
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode):
                    self.skipped["symlink"] += 1
                    if kind(relative):
                        self.analysis.issue("relevant_symlink_excluded", relative)
                    continue
                is_dir = stat.S_ISDIR(info.st_mode)
                if name in EXCLUDED or (name.startswith(".") and name != ".github" and kind(relative) != "environment"):
                    self.skipped["private_or_generated"] += 1
                    continue
                if ignored(relative, is_dir, patterns):
                    self.skipped["ignored"] += 1
                    continue
                if is_dir:
                    if len(relative.split("/")) > 32:
                        raise OverflowError("directory_depth_limit")
                    child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY, dir_fd=fd)
                    try:
                        yield from self._walk(child, relative, patterns)
                    finally:
                        os.close(child)
                elif stat.S_ISREG(info.st_mode) and (file_kind := kind(relative)):
                    self.files += 1
                    if self.files > self.limits.max_files:
                        raise OverflowError("file_count_limit")
                    if file_kind == "environment":
                        # Presence evidence only: never read/hash an environment value.
                        self.hash.update(relative.encode() + b"\0environment-presence\0")
                        yield relative, file_kind, None
                    else:
                        data = self._read(fd, name, relative, self.limits.max_file_bytes)
                        if data is not None:
                            yield relative, file_kind, data
                else:
                    self.skipped["unsupported_file"] += 1
            except OSError:
                self.analysis.issue("unreadable_or_changed_entry", relative)

    def collect(self):
        try:
            fd = _open_input(self.root)
            try:
                info = os.fstat(fd)
                if stat.S_ISDIR(info.st_mode):
                    yield from self._walk(fd, "", [])
                elif stat.S_ISREG(info.st_mode):
                    self.input_kind = "file"
                    name = PurePosixPath(self.root).name
                    file_kind = kind(name)
                    if file_kind == "environment":
                        self.hash.update(name.encode() + b"\0environment-presence\0")
                        self.files = 1
                        yield name, file_kind, None
                    elif file_kind:
                        parent = _open_input(str(PurePosixPath(os.path.abspath(self.root)).parent))
                        try:
                            data = self._read(parent, name, name, self.limits.max_file_bytes)
                            self.files = 1
                            if data is not None:
                                yield name, file_kind, data
                        finally:
                            os.close(parent)
                    else:
                        self.analysis.issue("unsupported_input")
                else:
                    self.analysis.issue("non_regular_input")
            finally:
                os.close(fd)
        except FileNotFoundError:
            self.analysis.issue("path_not_found")
        except OSError:
            self.analysis.issue("input_unreadable_or_symlink")
        except TimeoutError:
            self.analysis.issue("time_limit")
        except OverflowError as exc:
            self.analysis.issue(str(exc))

    @property
    def scope_fingerprint(self):
        return digest({"profile": "local-static", "limits": asdict(self.limits),
                       "exclusions": sorted(EXCLUDED), "ignore_patterns": self.ignores,
                       "input_kind": self.input_kind})

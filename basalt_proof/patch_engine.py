from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from typing import Iterable

from .models import PatchFileChange, PatchHunk, PatchStats


class PatchError(ValueError):
    """Raised when a patch is malformed, stale, or unsafe to apply."""


_HUNK_RE = re.compile(
    r"^@@\s+-(?P<old_start>\d+)(?:,(?P<old_count>\d+))?\s+"
    r"\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))?\s+@@"
)

_TEST_PATTERNS = (
    "tests/",
    "test/",
    "__tests__/",
)
_TEST_SUFFIXES = (
    ".test.js",
    ".test.jsx",
    ".test.ts",
    ".test.tsx",
    ".spec.js",
    ".spec.jsx",
    ".spec.ts",
    ".spec.tsx",
)


def patch_sha256(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def _clean_diff_path(raw: str) -> str:
    raw = raw.strip().split("\t", 1)[0]
    if raw == "/dev/null":
        return raw
    if raw.startswith(("a/", "b/")):
        raw = raw[2:]
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts or not raw or raw in {".", ".."}:
        raise PatchError(f"Unsafe patch path: {raw!r}")
    if any(part in {".git", ".basalt"} for part in path.parts):
        raise PatchError(f"Patch cannot modify Basalt or Git control data: {raw}")
    return path.as_posix()


def parse_unified_diff(text: str) -> list[PatchFileChange]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.strip():
        raise PatchError("Patch is empty.")
    if "GIT binary patch" in normalized or "Binary files " in normalized:
        raise PatchError("Binary patches are not supported.")

    lines = normalized.splitlines()
    changes: list[PatchFileChange] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("diff --git "):
            index += 1
            while index < len(lines) and not lines[index].startswith("--- "):
                if lines[index].startswith("diff --git "):
                    raise PatchError("Missing ---/+++ headers in patch.")
                index += 1
        elif not line.startswith("--- "):
            index += 1
            continue

        if index >= len(lines) or not lines[index].startswith("--- "):
            raise PatchError("Missing old-file header.")
        old_path = _clean_diff_path(lines[index][4:])
        index += 1
        if index >= len(lines) or not lines[index].startswith("+++ "):
            raise PatchError("Missing new-file header.")
        new_path = _clean_diff_path(lines[index][4:])
        index += 1

        if old_path == "/dev/null" and new_path == "/dev/null":
            raise PatchError("Patch cannot use /dev/null for both paths.")
        if old_path == "/dev/null":
            change_type = "add"
        elif new_path == "/dev/null":
            change_type = "delete"
        else:
            change_type = "modify"
            if old_path != new_path:
                raise PatchError("Renames are not supported in Phase 3 patches.")

        change = PatchFileChange(old_path=old_path, new_path=new_path, change_type=change_type)
        while index < len(lines):
            if lines[index].startswith("diff --git ") or lines[index].startswith("--- "):
                break
            if not lines[index].startswith("@@ "):
                if lines[index].strip() in {"", "\\ No newline at end of file"}:
                    index += 1
                    continue
                raise PatchError(f"Unexpected patch line: {lines[index]!r}")
            match = _HUNK_RE.match(lines[index])
            if not match:
                raise PatchError(f"Malformed hunk header: {lines[index]}")
            old_start = int(match.group("old_start"))
            old_count = int(match.group("old_count") or "1")
            new_start = int(match.group("new_start"))
            new_count = int(match.group("new_count") or "1")
            index += 1
            hunk_lines: list[str] = []
            old_seen = 0
            new_seen = 0
            while index < len(lines):
                current = lines[index]
                if current.startswith("@@ ") or current.startswith("diff --git ") or current.startswith("--- "):
                    break
                if current == "\\ No newline at end of file":
                    index += 1
                    continue
                if not current or current[0] not in {" ", "+", "-"}:
                    raise PatchError(f"Malformed hunk content: {current!r}")
                hunk_lines.append(current)
                if current[0] in {" ", "-"}:
                    old_seen += 1
                if current[0] in {" ", "+"}:
                    new_seen += 1
                index += 1
            if old_seen != old_count or new_seen != new_count:
                raise PatchError(
                    "Hunk line counts do not match header "
                    f"(expected -{old_count}/+{new_count}, got -{old_seen}/+{new_seen})."
                )
            change.hunks.append(
                PatchHunk(
                    old_start=old_start,
                    old_count=old_count,
                    new_start=new_start,
                    new_count=new_count,
                    lines=hunk_lines,
                )
            )
            change.additions += sum(1 for item in hunk_lines if item.startswith("+"))
            change.deletions += sum(1 for item in hunk_lines if item.startswith("-"))

        if not change.hunks:
            raise PatchError(f"Patch for {new_path if new_path != '/dev/null' else old_path} has no hunks.")
        changes.append(change)

    if not changes:
        raise PatchError("No file changes found in unified diff.")
    paths = [change.new_path if change.new_path != "/dev/null" else change.old_path for change in changes]
    if len(paths) != len(set(paths)):
        raise PatchError("A patch may contain only one file section per path.")
    return changes


def _is_test_path(path: str) -> bool:
    lowered = path.lower()
    name = PurePosixPath(lowered).name
    return (
        any(lowered.startswith(prefix) or f"/{prefix}" in lowered for prefix in _TEST_PATTERNS)
        or name.startswith("test_")
        or name.endswith("_test.py")
        or any(name.endswith(suffix) for suffix in _TEST_SUFFIXES)
    )


def patch_stats(changes: Iterable[PatchFileChange]) -> PatchStats:
    items = list(changes)
    paths = [item.new_path if item.new_path != "/dev/null" else item.old_path for item in items]
    additions = sum(item.additions for item in items)
    deletions = sum(item.deletions for item in items)
    return PatchStats(
        files_changed=len(items),
        additions=additions,
        deletions=deletions,
        changed_lines=additions + deletions,
        paths=paths,
        test_only=bool(paths) and all(_is_test_path(path) for path in paths),
        contains_binary=False,
    )


def added_lines(changes: Iterable[PatchFileChange]) -> list[tuple[str, int, str]]:
    result: list[tuple[str, int, str]] = []
    for change in changes:
        path = change.new_path if change.new_path != "/dev/null" else change.old_path
        for hunk in change.hunks:
            line_number = hunk.new_start
            for raw in hunk.lines:
                if raw.startswith("+"):
                    result.append((path, line_number, raw[1:]))
                    line_number += 1
                elif raw.startswith(" "):
                    line_number += 1
    return result


def _read_source(path: Path) -> tuple[list[str], bool]:
    data = path.read_bytes()
    if b"\x00" in data:
        raise PatchError(f"Cannot patch binary file: {path}")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PatchError(f"Cannot patch non-UTF-8 file: {path}") from exc
    return text.splitlines(), text.endswith("\n")


def _apply_change(repo: Path, change: PatchFileChange) -> Path:
    relative = change.new_path if change.new_path != "/dev/null" else change.old_path
    target = repo / relative
    resolved_repo = repo.resolve()
    resolved_parent = target.parent.resolve()
    if resolved_repo != resolved_parent and resolved_repo not in resolved_parent.parents:
        raise PatchError(f"Patch path escapes repository: {relative}")
    if target.is_symlink():
        raise PatchError(f"Refusing to patch symlink: {relative}")

    if change.change_type == "add":
        if target.exists():
            raise PatchError(f"New-file patch target already exists: {relative}")
        source_lines: list[str] = []
        had_newline = True
    else:
        if not target.exists() or not target.is_file():
            raise PatchError(f"Patch target does not exist: {relative}")
        source_lines, had_newline = _read_source(target)

    output: list[str] = []
    cursor = 0
    for hunk in change.hunks:
        expected_index = max(0, hunk.old_start - 1)
        if expected_index < cursor or expected_index > len(source_lines):
            raise PatchError(f"Hunk position is invalid for {relative}.")
        output.extend(source_lines[cursor:expected_index])
        source_index = expected_index
        for raw in hunk.lines:
            marker, content = raw[0], raw[1:]
            if marker in {" ", "-"}:
                if source_index >= len(source_lines) or source_lines[source_index] != content:
                    actual = source_lines[source_index] if source_index < len(source_lines) else "<EOF>"
                    raise PatchError(
                        f"Patch is stale for {relative} at source line {source_index + 1}: "
                        f"expected {content!r}, found {actual!r}."
                    )
                if marker == " ":
                    output.append(content)
                source_index += 1
            else:
                output.append(content)
        cursor = source_index
    output.extend(source_lines[cursor:])

    if change.change_type == "delete":
        if output:
            raise PatchError(f"Delete patch for {relative} did not remove all content.")
        target.unlink()
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(output)
    if output and (had_newline or change.change_type == "add"):
        text += "\n"
    target.write_text(text, encoding="utf-8")
    return target


def validate_patch_applies(repo: Path, changes: Iterable[PatchFileChange]) -> None:
    """Validate patch context without mutating the repository."""
    import tempfile

    repo = repo.resolve()
    with tempfile.TemporaryDirectory(prefix="basalt-patch-check-") as directory:
        temp_repo = Path(directory) / "repo"
        shutil.copytree(
            repo,
            temp_repo,
            ignore=shutil.ignore_patterns(".git", ".basalt", ".venv", "node_modules", ".basalt-deps"),
        )
        for change in changes:
            _apply_change(temp_repo, change)


def apply_patch(repo: Path, changes: Iterable[PatchFileChange]) -> list[str]:
    applied: list[str] = []
    for change in changes:
        target = _apply_change(repo.resolve(), change)
        applied.append(target.relative_to(repo.resolve()).as_posix())
    return applied


def create_backup(repo: Path, changes: Iterable[PatchFileChange], backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    for change in changes:
        relative = change.new_path if change.new_path != "/dev/null" else change.old_path
        source = repo / relative
        existed = source.exists()
        record: dict[str, object] = {"path": relative, "existed": existed}
        if existed:
            if not source.is_file() or source.is_symlink():
                raise PatchError(f"Cannot back up non-regular file: {relative}")
            destination = backup_dir / "files" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            record["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        records.append(record)
    manifest = backup_dir / "manifest.json"
    manifest.write_text(json.dumps(records, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def restore_backup(repo: Path, backup_dir: Path) -> list[str]:
    manifest = backup_dir / "manifest.json"
    if not manifest.exists():
        raise PatchError(f"Backup manifest not found: {manifest}")
    records = json.loads(manifest.read_text(encoding="utf-8"))
    restored: list[str] = []
    for record in records:
        relative = str(record["path"])
        target = repo / relative
        if bool(record["existed"]):
            source = backup_dir / "files" / relative
            if not source.exists():
                raise PatchError(f"Backup file missing: {source}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        elif target.exists():
            if target.is_file() or target.is_symlink():
                target.unlink()
            else:
                shutil.rmtree(target)
        restored.append(relative)
    return restored


def render_patch_summary(changes: Iterable[PatchFileChange]) -> str:
    items = list(changes)
    stats = patch_stats(items)
    lines = [
        "# Basalt Candidate Patch",
        "",
        f"- Files changed: `{stats.files_changed}`",
        f"- Additions: `{stats.additions}`",
        f"- Deletions: `{stats.deletions}`",
        f"- Test-only: `{stats.test_only}`",
        "",
        "## Files",
        "",
    ]
    for item in items:
        path = item.new_path if item.new_path != "/dev/null" else item.old_path
        lines.append(f"- `{item.change_type}` `{path}` (+{item.additions}/-{item.deletions})")
    return "\n".join(lines) + "\n"


def patch_as_dict(changes: Iterable[PatchFileChange]) -> list[dict[str, object]]:
    return [asdict(change) for change in changes]

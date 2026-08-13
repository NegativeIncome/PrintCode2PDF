from __future__ import annotations

import fnmatch
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from config import Config


@dataclass
class FileRecord:
    abs_path: Path | None
    rel_path: Path
    extension: str
    size_bytes: int
    skipped: bool = False
    skip_reason: str = ""
    content: bytes | None = None  # set for git-ref scans; None means read from abs_path

    def read_text(self) -> str:
        if self.content is not None:
            return self.content.decode("utf-8", errors="replace")
        try:
            return self.abs_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return "[Could not read file]"


def _is_likely_binary_bytes(data: bytes, sample: int = 8192) -> bool:
    chunk = data[:sample]
    # UTF-16 files (common from Visual Studio) have a BOM and null bytes — text, not binary
    if chunk[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return False
    if b"\x00" in chunk:
        return True
    try:
        chunk.decode("utf-8")
        return False
    except UnicodeDecodeError:
        return True


def _is_likely_binary(path: Path, sample: int = 8192) -> bool:
    try:
        return _is_likely_binary_bytes(path.read_bytes()[:sample], sample)
    except OSError:
        return True


def _matches_any_pattern(posix_rel: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if fnmatch.fnmatch(posix_rel, pattern):
            return True
        # Patterns without slashes match against just the filename
        if "/" not in pattern and fnmatch.fnmatch(Path(posix_rel).name, pattern):
            return True
        # Patterns like "obj/**" should match at any depth ("src/obj/file")
        if "/" in pattern:
            parts = posix_rel.split("/")
            for i in range(1, len(parts)):
                if fnmatch.fnmatch("/".join(parts[i:]), pattern):
                    return True
    return False


def scan(config: Config) -> tuple[list[FileRecord], list[FileRecord]]:
    """Return (included_records, skipped_records)."""
    root = config.project.root
    max_bytes = config.files.max_file_size_kb * 1024

    included: list[FileRecord] = []
    skipped: list[FileRecord] = []

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dir_abs = Path(dirpath)
        dir_rel = dir_abs.relative_to(root)
        dir_posix = PurePosixPath(dir_rel).as_posix()

        # Prune excluded directories in-place to avoid descending into them
        dirnames[:] = [
            d for d in dirnames
            if not _matches_any_pattern(
                PurePosixPath(dir_rel / d).as_posix() + "/placeholder",
                [p for p in config.files.exclude_patterns if "**" in p or "/" in p],
            )
        ]

        for filename in sorted(filenames):
            file_abs = dir_abs / filename
            file_rel = dir_rel / filename
            posix_rel = PurePosixPath(file_rel).as_posix()
            ext = file_abs.suffix.lower()

            if ext not in config.files.include_extensions:
                continue

            if _matches_any_pattern(posix_rel, config.files.exclude_patterns):
                continue

            try:
                size = file_abs.stat().st_size
            except OSError:
                continue

            record = FileRecord(
                abs_path=file_abs,
                rel_path=file_rel,
                extension=ext,
                size_bytes=size,
            )

            if max_bytes > 0 and size > max_bytes:
                record.skipped = True
                record.skip_reason = f"exceeds {config.files.max_file_size_kb} KB limit ({size // 1024} KB)"
                skipped.append(record)
                continue

            if config.files.skip_binary_files and _is_likely_binary(file_abs):
                record.skipped = True
                record.skip_reason = "detected as binary"
                skipped.append(record)
                continue

            included.append(record)

    # Sort by path components for natural directory grouping
    included.sort(key=lambda r: (r.rel_path.parent.parts, r.rel_path.name))
    skipped.sort(key=lambda r: (r.rel_path.parent.parts, r.rel_path.name))

    return included, skipped


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
    )


def _resolve_git_root(root: Path) -> Path:
    result = _git(["rev-parse", "--show-toplevel"], root)
    if result.returncode != 0:
        sys.exit(
            f"Error: {root} is not inside a git repository "
            f"(--ref requires one):\n{result.stderr.decode(errors='replace').strip()}"
        )
    return Path(result.stdout.decode().strip())


def scan_git_ref(config: Config) -> tuple[list[FileRecord], list[FileRecord]]:
    """Same contract as scan(), but reads file contents from a git ref
    (branch/tag/commit) via git plumbing instead of the working-tree
    filesystem, so it works regardless of which branch is checked out."""
    root = config.project.root
    ref = config.project.ref
    max_bytes = config.files.max_file_size_kb * 1024

    repo_root = _resolve_git_root(root)

    verify = _git(["rev-parse", "--verify", f"{ref}^{{commit}}"], repo_root)
    if verify.returncode != 0:
        sys.exit(f"Error: git ref not found: {ref}")

    # `root` may be the repo root itself, or a subdirectory of it — only
    # include paths under that subdirectory, re-relativized to `root`.
    try:
        prefix = root.resolve().relative_to(repo_root)
    except ValueError:
        prefix = Path(".")
    prefix_posix = PurePosixPath(prefix).as_posix()
    under_prefix = prefix_posix not in (".", "")

    ls = _git(["ls-tree", "-r", "-l", "-z", ref], repo_root)
    if ls.returncode != 0:
        sys.exit(f"Error listing files at ref {ref}:\n{ls.stderr.decode(errors='replace')}")

    included: list[FileRecord] = []
    skipped: list[FileRecord] = []

    for entry in ls.stdout.decode("utf-8", errors="replace").split("\0"):
        if not entry:
            continue
        # format: "<mode> <type> <object> <size>\t<path>"
        meta, _, path = entry.partition("\t")
        parts = meta.split()
        if len(parts) != 4:
            continue
        _mode, obj_type, obj_hash, size_str = parts
        if obj_type != "blob":
            continue

        if under_prefix:
            if not (path == prefix_posix or path.startswith(prefix_posix + "/")):
                continue
            posix_rel = path[len(prefix_posix) + 1:]
        else:
            posix_rel = path

        rel_path = Path(posix_rel)
        ext = rel_path.suffix.lower()

        if ext not in config.files.include_extensions:
            continue
        if _matches_any_pattern(posix_rel, config.files.exclude_patterns):
            continue

        size = int(size_str)
        record = FileRecord(
            abs_path=None,
            rel_path=rel_path,
            extension=ext,
            size_bytes=size,
        )

        if max_bytes > 0 and size > max_bytes:
            record.skipped = True
            record.skip_reason = f"exceeds {config.files.max_file_size_kb} KB limit ({size // 1024} KB)"
            skipped.append(record)
            continue

        blob = _git(["cat-file", "-p", obj_hash], repo_root)
        if blob.returncode != 0:
            record.skipped = True
            record.skip_reason = f"git cat-file failed: {blob.stderr.decode(errors='replace').strip()}"
            skipped.append(record)
            continue

        if config.files.skip_binary_files and _is_likely_binary_bytes(blob.stdout):
            record.skipped = True
            record.skip_reason = "detected as binary"
            skipped.append(record)
            continue

        record.content = blob.stdout
        included.append(record)

    included.sort(key=lambda r: (r.rel_path.parent.parts, r.rel_path.name))
    skipped.sort(key=lambda r: (r.rel_path.parent.parts, r.rel_path.name))

    return included, skipped

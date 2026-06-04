from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from config import Config


@dataclass
class FileRecord:
    abs_path: Path
    rel_path: Path
    extension: str
    size_bytes: int
    skipped: bool = False
    skip_reason: str = ""


def _is_likely_binary(path: Path, sample: int = 8192) -> bool:
    try:
        chunk = path.read_bytes()[:sample]
        # UTF-16 files (common from Visual Studio) have a BOM and null bytes — text, not binary
        if chunk[:2] in (b"\xff\xfe", b"\xfe\xff"):
            return False
        if b"\x00" in chunk:
            return True
        chunk.decode("utf-8")
        return False
    except (UnicodeDecodeError, OSError):
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

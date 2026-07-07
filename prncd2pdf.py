#!/usr/bin/env python3
"""Source Code to PDF/EPUB Printer.

Usage:
    python prncd2pdf.py                          # uses ./prncd2pdf.toml
    python prncd2pdf.py --config other.toml
    python prncd2pdf.py --root C:\\myproject
    python prncd2pdf.py --root . --theme monokai --output report.pdf
    python prncd2pdf.py --root . --epub
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print project source code to a PDF or EPUB with a table of contents.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        default=None,
        help="Path to TOML config file (default: prncd2pdf.toml in current directory)",
    )
    parser.add_argument(
        "--root",
        metavar="DIR",
        default=None,
        help="Project root directory to scan (overrides config)",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        default=None,
        help="Output PDF path (overrides config). Tokens: {root_name}, {date}",
    )
    parser.add_argument(
        "--theme",
        metavar="NAME",
        default=None,
        help="Pygments syntax theme (overrides config). E.g. monokai, vs, friendly",
    )
    parser.add_argument(
        "--list-themes",
        action="store_true",
        help="Print all available Pygments themes and exit",
    )
    parser.add_argument(
        "--extensions",
        metavar="EXT",
        nargs="+",
        default=None,
        help="File extensions to include, e.g. .py .js .ts (overrides config)",
    )
    parser.add_argument(
        "--no-line-numbers",
        action="store_true",
        help="Disable line numbers in code blocks",
    )
    parser.add_argument(
        "--exclude",
        metavar="PATTERN",
        nargs="+",
        default=None,
        help="Extra glob patterns to exclude, e.g. 'Platforms/**' '.vs/**' (appended to config)",
    )
    parser.add_argument(
        "--epub",
        action="store_true",
        help="Generate an EPUB instead of a PDF (reflowable, navigable on e-readers)",
    )

    args = parser.parse_args()

    if args.list_themes:
        from pygments.styles import get_all_styles
        for name in sorted(get_all_styles()):
            print(name)
        return

    # Locate config file
    if args.config:
        config_path = Path(args.config).resolve()
        if not config_path.exists():
            sys.exit(f"Config file not found: {config_path}")
    else:
        config_path = Path.cwd() / "prncd2pdf.toml"
        if not config_path.exists():
            # Fall back to the directory of this script
            config_path = Path(__file__).parent / "prncd2pdf.toml"

    # Build CLI overrides dict (only set keys that were explicitly passed)
    overrides: dict = {}
    if args.root:
        overrides.setdefault("project", {})["root"] = str(Path(args.root).resolve())
    if args.output:
        overrides.setdefault("project", {})["output"] = args.output
    if args.theme:
        overrides.setdefault("pdf", {})["syntax_theme"] = args.theme
    if args.extensions:
        overrides.setdefault("files", {})["include_extensions"] = args.extensions
    if args.no_line_numbers:
        overrides.setdefault("pdf", {})["line_numbers"] = False

    from config import load_config
    config = load_config(config_path, overrides if overrides else None)

    if args.exclude:
        config.files.exclude_patterns.extend(args.exclude)

    if args.epub:
        from builder import build_epub
        build_epub(config)
    else:
        from builder import build
        build(config)


if __name__ == "__main__":
    main()

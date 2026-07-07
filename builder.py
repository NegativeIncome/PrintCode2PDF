from __future__ import annotations

import sys
from pathlib import Path, PurePosixPath

from reportlab.lib.pagesizes import A3, A4, LEGAL, LETTER
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate

from config import Config
from renderer import build_story
from scanner import scan

_PAGE_SIZES = {
    "a4": A4,
    "letter": LETTER,
    "a3": A3,
    "legal": LEGAL,
}


def _draw_page_number(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(doc.pagesize[0] / 2, 10 * mm, str(canvas.getPageNumber()))
    canvas.restoreState()


def build(config: Config) -> Path:
    if not config.project.root.exists():
        sys.exit(f"Error: root directory does not exist: {config.project.root}")

    print(f"Scanning: {config.project.root}")
    records, skipped = scan(config)

    if not records:
        sys.exit(
            "No files found matching the configured extensions.\n"
            "Check 'include_extensions' and 'exclude_patterns' in your config."
        )

    print(f"  Found {len(records)} files to include, {len(skipped)} skipped.")
    for r in skipped:
        print(f"  [skip] {PurePosixPath(r.rel_path).as_posix()} — {r.skip_reason}")

    root_name = config.project.root.name or "project"

    output_path = config.resolve_output()
    if not output_path.is_absolute():
        output_path = (Path.cwd() / output_path).resolve()
    if output_path.is_dir():
        from datetime import date
        output_path = output_path / f"output_{root_name}_{date.today().isoformat()}.pdf"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    page_size = _PAGE_SIZES.get(config.pdf.page_size.lower(), A4)
    bottom_margin = 20 * mm if config.pdf.page_numbers else 15 * mm

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=page_size,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=bottom_margin,
    )

    print("Building story...")
    story = build_story(records, skipped, config, root_name)

    print("Rendering PDF...")
    if config.pdf.page_numbers:
        doc.build(story, onFirstPage=_draw_page_number, onLaterPages=_draw_page_number)
    else:
        doc.build(story)

    size_kb = output_path.stat().st_size // 1024
    print(f"Done: {output_path}  ({size_kb} KB)")
    return output_path


def build_epub(config: Config) -> Path:
    if not config.project.root.exists():
        sys.exit(f"Error: root directory does not exist: {config.project.root}")

    print(f"Scanning: {config.project.root}")
    records, skipped = scan(config)

    if not records:
        sys.exit(
            "No files found matching the configured extensions.\n"
            "Check 'include_extensions' and 'exclude_patterns' in your config."
        )

    print(f"  Found {len(records)} files to include, {len(skipped)} skipped.")
    for r in skipped:
        print(f"  [skip] {PurePosixPath(r.rel_path).as_posix()} — {r.skip_reason}")

    root_name = config.project.root.name or "project"

    output_path = config.resolve_output()
    if not output_path.is_absolute():
        output_path = (Path.cwd() / output_path).resolve()
    if output_path.is_dir():
        from datetime import date
        output_path = output_path / f"output_{root_name}_{date.today().isoformat()}.epub"
    else:
        output_path = output_path.with_suffix(".epub")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    from epub_renderer import build_epub_book
    print("Building EPUB...")
    book = build_epub_book(records, skipped, config, root_name)

    from ebooklib import epub
    print("Writing EPUB...")
    epub.write_epub(str(output_path), book, {"epub3_pages": False})

    size_kb = output_path.stat().st_size // 1024
    print(f"Done: {output_path}  ({size_kb} KB)")
    return output_path

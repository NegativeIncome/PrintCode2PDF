from __future__ import annotations

from datetime import date
from html import escape
from pathlib import PurePosixPath

from pygments import lex
from pygments.lexers import TextLexer, get_lexer_for_filename
from pygments.styles import get_style_by_name
from pygments.util import ClassNotFound

from config import Config
from scanner import FileRecord

_CSS = """\
body { font-family: Georgia, 'Times New Roman', serif; margin: 1em; }
h1.file-path {
    font-family: 'Courier New', Courier, monospace;
    font-size: 0.9em;
    background: #f0f4f8;
    padding: 0.4em 0.7em;
    border-left: 3px solid #2563eb;
    word-break: break-all;
    margin: 0 0 0.2em 0;
}
p.file-meta { color: #666; font-size: 0.8em; margin: 0 0 0.6em 0.5em; }
pre.code {
    font-family: 'Courier New', Courier, monospace;
    font-size: 0.82em;
    line-height: 1.35;
    padding: 0.5em 0.6em;
    white-space: pre-wrap;
    word-break: break-all;
    margin: 0;
    border-radius: 0 0 3px 3px;
}
.ln { color: #aaaaaa; -webkit-user-select: none; user-select: none; }
h2.toc-title { font-size: 1.2em; margin-bottom: 0.8em; }
ul.toc-list { list-style: none; padding: 0; font-family: 'Courier New', Courier, monospace; font-size: 0.85em; }
ul.toc-list li { padding: 0.15em 0; }
ul.toc-list li a { color: #2563eb; text-decoration: none; }
h2.skipped-title { color: #b45309; }
ul.skipped-list { font-family: 'Courier New', Courier, monospace; font-size: 0.82em; }
ul.skipped-list li { color: #555; }
ul.skipped-list li em { color: #999; }
"""


def _get_lexer(record: FileRecord):
    try:
        return get_lexer_for_filename(record.rel_path.name, stripall=True)
    except ClassNotFound:
        return TextLexer(stripall=True)


def _fmt_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _tokenize_lines(code: str, lexer) -> list[list[tuple]]:
    code = code.replace("\r\n", "\n").replace("\r", "\n")
    lines: list[list[tuple]] = [[]]
    for ttype, value in lex(code, lexer):
        if "\n" not in value:
            lines[-1].append((ttype, value))
        else:
            parts = value.split("\n")
            for i, part in enumerate(parts):
                if i > 0:
                    lines.append([])
                if part:
                    lines[-1].append((ttype, part))
    if lines and not lines[-1]:
        lines.pop()
    return lines


def _span_style(info: dict) -> str:
    parts = []
    color = info.get("color")
    if color:
        parts.append(f"color: #{color}")
    if info.get("bold"):
        parts.append("font-weight: bold")
    if info.get("italic"):
        parts.append("font-style: italic")
    bgcolor = info.get("bgcolor")
    if bgcolor:
        parts.append(f"background-color: #{bgcolor}")
    return "; ".join(parts)


def _render_line(line_tokens: list[tuple], pygments_style, line_num: int | None) -> str:
    parts = []
    if line_num is not None:
        parts.append(f'<span class="ln">{escape(f"{line_num:4d}  ")}</span>')
    for ttype, value in line_tokens:
        text = escape(value.expandtabs(4))
        if not text:
            continue
        t = ttype
        while t:
            try:
                info = pygments_style.style_for_token(t)
                break
            except KeyError:
                t = t.parent
        else:
            info = {}
        style = _span_style(info)
        parts.append(f'<span style="{style}">{text}</span>' if style else text)
    return "".join(parts) if parts else " "


def _xhtml(title: str, body_html: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">\n'
        '<head>\n'
        '  <meta charset="utf-8"/>\n'
        f'  <title>{escape(title)}</title>\n'
        '  <link rel="stylesheet" type="text/css" href="style/main.css"/>\n'
        '</head>\n'
        f'<body>\n{body_html}</body>\n</html>\n'
    )


def build_epub_book(
    records: list[FileRecord],
    skipped: list[FileRecord],
    config: Config,
    root_name: str,
):
    try:
        from ebooklib import epub
    except ImportError:
        import sys
        sys.exit("ebooklib is required for EPUB output: pip install ebooklib")

    try:
        pstyle = get_style_by_name(config.pdf.syntax_theme)
    except Exception:
        pstyle = get_style_by_name("friendly")

    bg_hex = getattr(pstyle, "background_color", None) or "#f8f8f8"
    today = date.today().isoformat()

    book = epub.EpubBook()
    book.set_identifier(f"printcode2pdf-{root_name}-{today}")
    book.set_title(root_name)
    book.set_language("en")

    css_item = epub.EpubItem(
        uid="style",
        file_name="style/main.css",
        media_type="text/css",
        content=_CSS,
    )
    book.add_item(css_item)

    chapters: list = []
    toc_links: list = []

    # Cover
    cover_body = (
        f'<h1>{escape(root_name)}</h1>\n'
        f'<p>Source Code Report</p>\n'
        f'<p>Generated: {today}</p>\n'
        f'<p>Files included: {len(records)}</p>\n'
    )
    if skipped:
        cover_body += f'<p>Files skipped: {len(skipped)}</p>\n'
    cover_ch = epub.EpubHtml(title=root_name, file_name="cover.xhtml", lang="en")
    cover_ch.content = _xhtml(root_name, cover_body).encode("utf-8")
    book.add_item(cover_ch)
    chapters.append(cover_ch)
    toc_links.append(epub.Link("cover.xhtml", root_name, "cover"))

    # In-book TOC page (hyperlinked file list)
    toc_entries = "".join(
        f'<li><a href="file_{i:04d}.xhtml">{escape(PurePosixPath(r.rel_path).as_posix())}</a></li>\n'
        for i, r in enumerate(records)
    )
    toc_body = (
        f'<h2 class="toc-title">{escape(config.toc.title)}</h2>\n'
        f'<ul class="toc-list">\n{toc_entries}</ul>\n'
    )
    toc_ch = epub.EpubHtml(title=config.toc.title, file_name="toc.xhtml", lang="en")
    toc_ch.content = _xhtml(config.toc.title, toc_body).encode("utf-8")
    book.add_item(toc_ch)
    chapters.append(toc_ch)
    toc_links.append(epub.Link("toc.xhtml", config.toc.title, "toc"))

    # File chapters
    for i, record in enumerate(records):
        display = PurePosixPath(record.rel_path).as_posix()

        code_text = record.read_text()

        line_count = code_text.count("\n")
        lexer = _get_lexer(record)
        tokenized = _tokenize_lines(code_text, lexer)

        lines_html = []
        for idx, line_tokens in enumerate(tokenized):
            ln = idx + 1 if config.pdf.line_numbers else None
            lines_html.append(_render_line(line_tokens, pstyle, ln))

        body = (
            f'<h1 class="file-path">{escape(display)}</h1>\n'
            f'<p class="file-meta">{_fmt_size(record.size_bytes)} &#x2022; {line_count} lines</p>\n'
            f'<pre class="code" style="background-color: {bg_hex};">'
            + "\n".join(lines_html)
            + "</pre>\n"
        )

        ch = epub.EpubHtml(title=display, file_name=f"file_{i:04d}.xhtml", lang="en")
        ch.content = _xhtml(display, body).encode("utf-8")
        book.add_item(ch)
        chapters.append(ch)
        toc_links.append(epub.Link(f"file_{i:04d}.xhtml", display, f"file-{i}"))

    # Skipped files appendix
    if skipped:
        skip_entries = "".join(
            f'<li>{escape(PurePosixPath(r.rel_path).as_posix())} '
            f'<em>({escape(r.skip_reason)})</em></li>\n'
            for r in skipped
        )
        skip_body = (
            f'<h2 class="skipped-title">Skipped Files ({len(skipped)})</h2>\n'
            f'<ul class="skipped-list">\n{skip_entries}</ul>\n'
        )
        skip_ch = epub.EpubHtml(
            title=f"Skipped Files ({len(skipped)})",
            file_name="skipped.xhtml",
            lang="en",
        )
        skip_ch.content = _xhtml("Skipped Files", skip_body).encode("utf-8")
        book.add_item(skip_ch)
        chapters.append(skip_ch)
        toc_links.append(epub.Link("skipped.xhtml", f"Skipped Files ({len(skipped)})", "skipped"))

    book.toc = toc_links
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav"] + chapters

    return book

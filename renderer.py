from __future__ import annotations

from datetime import date
from pathlib import PurePosixPath

from pygments import lex
from pygments.lexers import TextLexer, get_lexer_for_filename
from pygments.styles import get_style_by_name
from pygments.util import ClassNotFound

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, PageBreak, Paragraph, Spacer
from reportlab.platypus.flowables import AnchorFlowable, Flowable

from config import Config
from scanner import FileRecord


class GoToLink(Flowable):
    """Paragraph with a proper internal /GoTo PDF link (not /URI)."""
    def __init__(self, text: str, dest: str, style):
        Flowable.__init__(self)
        self._para = Paragraph(text, style)
        self._dest = dest

    def wrap(self, avail_w, avail_h):
        return self._para.wrap(avail_w, avail_h)

    def draw(self):
        self._para.drawOn(self.canv, 0, 0)
        w, h = self._para.width, self._para.height
        # linkAbsolute ignores canvas transforms — extract absolute page position
        ctm = self.canv._currentMatrix
        x0, y0 = ctm[4], ctm[5]
        self.canv.linkAbsolute("", self._dest, Rect=(x0, y0, x0 + w, y0 + h))


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _hex(color_str: str | None) -> str | None:
    if not color_str:
        return None
    return f"#{color_str}" if not color_str.startswith("#") else color_str


def _get_lexer(record: FileRecord):
    try:
        return get_lexer_for_filename(record.rel_path.name, stripall=True)
    except ClassNotFound:
        return TextLexer(stripall=True)


def _tokenize_lines(code: str, lexer) -> list[list[tuple]]:
    """Split Pygments token stream into per-line token lists."""
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


def _line_markup(
    line_tokens: list[tuple],
    pygments_style,
    line_num: int | None,
) -> str:
    parts = []
    if line_num is not None:
        num = _xml_escape(f"{line_num:4d}  ")
        parts.append(f'<font color="#aaaaaa">{num}</font>')
    for ttype, value in line_tokens:
        escaped = _xml_escape(value.expandtabs(4))
        if not escaped:
            continue
        info = pygments_style.style_for_token(ttype)
        color = _hex(info.get("color"))
        bold = info.get("bold", False)
        italic = info.get("italic", False)
        text = escaped
        if color:
            text = f'<font color="{color}">{text}</font>'
        if bold:
            text = f"<b>{text}</b>"
        if italic:
            text = f"<i>{text}</i>"
        parts.append(text)
    return "".join(parts) if parts else "&nbsp;"


def _fmt_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def build_story(
    records: list[FileRecord],
    skipped: list[FileRecord],
    config: Config,
    root_name: str,
) -> list:
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "CoverTitle",
        fontName="Helvetica-Bold",
        fontSize=28,
        spaceAfter=12,
        textColor=HexColor("#1a1a2e"),
        alignment=TA_LEFT,
    )
    subtitle_style = ParagraphStyle(
        "CoverSub",
        fontName="Helvetica",
        fontSize=11,
        spaceAfter=6,
        textColor=HexColor("#555555"),
    )
    toc_heading_style = ParagraphStyle(
        "TocHeading",
        fontName="Helvetica-Bold",
        fontSize=18,
        spaceAfter=10,
        spaceBefore=0,
        textColor=HexColor("#1a1a2e"),
    )
    toc_entry_style = ParagraphStyle(
        "TocEntry",
        fontName="Courier",
        fontSize=9,
        spaceAfter=2,
        spaceBefore=0,
        textColor=HexColor("#2563eb"),
        leftIndent=8,
    )
    file_header_style = ParagraphStyle(
        "FileHeader",
        fontName="Courier-Bold",
        fontSize=10,
        spaceAfter=2,
        spaceBefore=0,
        textColor=HexColor("#1a1a2e"),
        backColor=HexColor("#f0f4f8"),
        borderPadding=(6, 10, 6, 10),
    )
    file_meta_style = ParagraphStyle(
        "FileMeta",
        fontName="Helvetica",
        fontSize=8,
        spaceAfter=4,
        spaceBefore=0,
        textColor=HexColor("#666666"),
        leftIndent=8,
    )

    try:
        pstyle = get_style_by_name(config.pdf.syntax_theme)
    except Exception:
        pstyle = get_style_by_name("friendly")

    bg_hex = getattr(pstyle, "background_color", None) or "#f8f8f8"
    code_bg = HexColor(bg_hex)

    code_style = ParagraphStyle(
        "Code",
        fontName="Courier",
        fontSize=config.pdf.code_font_size_pt,
        leading=config.pdf.code_font_size_pt * 1.3,
        spaceAfter=0,
        spaceBefore=0,
        leftIndent=4,
        backColor=code_bg,
        wordWrap="CJK",
    )
    skip_heading_style = ParagraphStyle(
        "SkipHeading",
        fontName="Helvetica-Bold",
        fontSize=14,
        textColor=HexColor("#b45309"),
        spaceAfter=8,
    )
    skip_item_style = ParagraphStyle(
        "SkipItem",
        fontName="Courier",
        fontSize=8,
        spaceAfter=2,
        textColor=HexColor("#555555"),
    )

    story = []
    today = date.today().isoformat()

    # Cover page
    story.append(Spacer(1, 60 * mm))
    story.append(Paragraph(_xml_escape(root_name), title_style))
    story.append(Paragraph("Source Code Report", subtitle_style))
    story.append(
        HRFlowable(
            width="100%", thickness=1, color=HexColor("#cccccc"), spaceAfter=12
        )
    )
    story.append(Paragraph(f"Generated: {today}", subtitle_style))
    story.append(Paragraph(f"Files included: {len(records)}", subtitle_style))
    if skipped:
        story.append(Paragraph(f"Files skipped: {len(skipped)}", subtitle_style))
    story.append(PageBreak())

    # TOC page
    story.append(Paragraph(config.toc.title, toc_heading_style))
    story.append(
        HRFlowable(
            width="100%", thickness=2, color=HexColor("#1a1a2e"), spaceAfter=8
        )
    )
    for i, record in enumerate(records):
        display = PurePosixPath(record.rel_path).as_posix()
        story.append(GoToLink(_xml_escape(display), f"file-{i}", toc_entry_style))
    story.append(PageBreak())

    # File sections
    for i, record in enumerate(records):
        display = PurePosixPath(record.rel_path).as_posix()

        story.append(AnchorFlowable(f"file-{i}"))
        story.append(Paragraph(_xml_escape(display), file_header_style))

        try:
            code_text = record.abs_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            code_text = "[Could not read file]"

        line_count = code_text.count("\n")
        story.append(
            Paragraph(
                f"{_fmt_size(record.size_bytes)} &bull; {line_count} lines",
                file_meta_style,
            )
        )

        lexer = _get_lexer(record)
        tokenized = _tokenize_lines(code_text, lexer)

        for idx, line_tokens in enumerate(tokenized):
            ln = idx + 1 if config.pdf.line_numbers else None
            markup = _line_markup(line_tokens, pstyle, ln)
            story.append(Paragraph(markup, code_style))

        if i < len(records) - 1:
            story.append(PageBreak())

    # Skipped files
    if skipped:
        story.append(PageBreak())
        story.append(
            Paragraph(f"Skipped Files ({len(skipped)})", skip_heading_style)
        )
        story.append(
            HRFlowable(
                width="100%", thickness=1, color=HexColor("#b45309"), spaceAfter=8
            )
        )
        for r in skipped:
            display = PurePosixPath(r.rel_path).as_posix()
            story.append(
                Paragraph(
                    f'{_xml_escape(display)}  <font color="#999999">'
                    f"<i>({_xml_escape(r.skip_reason)})</i></font>",
                    skip_item_style,
                )
            )

    return story

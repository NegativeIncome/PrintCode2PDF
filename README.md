# PrintCode2PDF

CLI tool that scans a project directory and renders its source code to a PDF or EPUB with a clickable table of contents.  I wrote this so that I could read code on my Boox device and make notes.  But it should work for other environments.

## Features

- Recursive directory scan with extension/pattern/size/binary filtering
- Syntax-highlighted code sections (via Pygments), with `--list-themes` to browse all available styles
- PDF output with a clickable table of contents (PDF GoTo links — works in Edge, Acrobat, etc.), cover page, and skipped-files appendix
- EPUB output for e-readers, with a reflowable table of contents (EPUB3 nav + EPUB2 NCX fallback), each entry linking to its file
- Print code from a git branch, tag, or commit that isn't checked out, via `--ref` (reads file contents straight from git's object store, so your working tree is untouched)
- Configurable via `printcode2pdf.toml` (page size, fonts, syntax theme, line numbers, page numbers, TOC title) with CLI flags to override per-run

## Requirements

- Python 3.8+
- `pip install -r requirements.txt`

Dependencies: `pygments>=2.17`, `reportlab>=4.0`, `ebooklib` (for `--epub`), `tomli` (Python < 3.11)

## Usage

```
python printcode2pdf.py [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--root DIR` | Project root directory to scan (overrides config; default: current directory) |
| `--config PATH` | Path to TOML config file (default: `printcode2pdf.toml` in current directory) |
| `--ref REF` | Git branch, tag, or commit to scan instead of the working tree (root must be inside a git repo) |
| `--output PATH` | Output path (overrides config). Tokens: `{root_name}`, `{date}` |
| `--epub` | Generate an EPUB instead of a PDF (reflowable, navigable on e-readers) |
| `--theme NAME` | Pygments syntax theme (overrides config), e.g. `monokai`, `vs`, `friendly` |
| `--list-themes` | Print all available Pygments themes and exit |
| `--extensions EXT [EXT ...]` | File extensions to include, e.g. `.py .js .ts` (overrides config) |
| `--exclude PATTERN [PATTERN ...]` | Extra glob patterns to exclude, e.g. `'Platforms/**' '.vs/**'` (appended to config) |
| `--no-line-numbers` | Disable line numbers in code blocks |

Examples:

```
python printcode2pdf.py                                       # uses ./printcode2pdf.toml
python printcode2pdf.py --root . --theme monokai --output report.pdf
python printcode2pdf.py --root . --epub
python printcode2pdf.py --root C:\myproject --ref some-branch  # print a branch without checking it out
```

## Configuration

Copy or edit `printcode2pdf.toml` in your project root:

```toml
[project]
root = "."
output = "./output_{root_name}_{date}.pdf"
# ref = "some-branch"          # optional: same as --ref

[files]
include_extensions = [".py", ".js", ".ts", ".go", ".rs"]  # see config.py for the full default list
exclude_patterns = ["__pycache__/**", ".git/**", "node_modules/**"]
max_file_size_kb = 1024
skip_binary_files = true

[pdf]
page_size = "A4"                # A4, LETTER, A3, LEGAL
code_font = "Courier New, Courier, monospace"
code_font_size_pt = 9
syntax_theme = "friendly"
line_numbers = true
page_numbers = true

[toc]
title = "Table of Contents"
```

## Architecture

| File | Role |
|------|------|
| `printcode2pdf.py` | CLI entry point, arg parsing |
| `config.py` | TOML config loading with CLI override merging |
| `scanner.py` | Directory walker with filtering; `scan_git_ref()` reads file contents from a git ref via `ls-tree`/`cat-file` for `--ref` |
| `renderer.py` | ReportLab story builder (cover, TOC, code, appendix) for PDF output |
| `epub_renderer.py` | EPUB builder (cover, nav/TOC, per-file XHTML pages) for `--epub` output |
| `builder.py` | Orchestrates scan → render → write PDF or EPUB |

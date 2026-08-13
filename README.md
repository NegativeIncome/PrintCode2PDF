# PrintCode2PDF

CLI tool that scans a project directory and renders its source code to a PDF with a clickable table of contents.

## Features

- Recursive directory scan with extension/pattern/size/binary filtering
- Syntax-highlighted code sections (via Pygments)
- Clickable table of contents with PDF GoTo links (works in Edge, Acrobat, etc.)
- Cover page and skipped-files appendix
- Configurable via `printcode2pdf.toml` (page size, fonts, margins, TOC depth, page numbers)
- Will print code from an NON checked out branch with a command line switch

## Requirements

- Python 3.8+
- `pip install -r requirements.txt`

Dependencies: `pygments>=2.17`, `reportlab>=4.0`, `tomli` (Python < 3.11)

## Usage

```
python printcode2pdf.py [OPTIONS] [DIRECTORY]
```

| Option | Description |
|--------|-------------|
| `DIRECTORY` | Root directory to scan (default: current directory) |
| `--output FILE` | Output PDF path (default: `output_<dir>_<date>.pdf`) |
| `--config FILE` | Path to TOML config (default: `printcode2pdf.toml` in target dir) |

## Configuration

Copy or edit `printcode2pdf.toml` in your project root:

```toml
[pdf]
page_size = "A4"        # A4, LETTER, A3, LEGAL
page_numbers = true

[scan]
extensions = [".py", ".js", ".ts", ".go", ".rs"]
exclude_patterns = ["__pycache__", ".git", "node_modules"]
max_file_size_kb = 500
```

## Architecture

| File | Role |
|------|------|
| `printcode2pdf.py` | CLI entry point, arg parsing |
| `config.py` | TOML config loading with CLI override merging |
| `scanner.py` | Directory walker with filtering |
| `renderer.py` | ReportLab story builder (cover, TOC, code, appendix) |
| `builder.py` | Orchestrates scan → render → write PDF |

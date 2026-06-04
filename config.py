from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        sys.exit("Python < 3.11 requires 'tomli': pip install tomli")


@dataclass
class ProjectConfig:
    root: Path
    output: str


@dataclass
class FilesConfig:
    include_extensions: list[str]
    exclude_patterns: list[str]
    max_file_size_kb: int
    skip_binary_files: bool


@dataclass
class PdfConfig:
    page_size: str
    code_font: str
    code_font_size_pt: int
    syntax_theme: str
    line_numbers: bool
    page_numbers: bool


@dataclass
class TocConfig:
    title: str


@dataclass
class Config:
    project: ProjectConfig
    files: FilesConfig
    pdf: PdfConfig
    toc: TocConfig

    def resolve_output(self) -> Path:
        from datetime import date
        tokens = {
            "root_name": self.project.root.name or "project",
            "date": date.today().isoformat(),
        }
        resolved = self.project.output
        for key, val in tokens.items():
            resolved = resolved.replace(f"{{{key}}}", val)
        return Path(resolved)


_DEFAULTS: dict = {
    "project": {
        "root": ".",
        "output": "./output_{root_name}_{date}.pdf",
    },
    "files": {
        "include_extensions": [
            ".py", ".js", ".ts", ".jsx", ".tsx",
            ".cs", ".go", ".java", ".rs",
            ".cpp", ".c", ".h", ".hpp",
            ".rb", ".php", ".swift", ".kt",
            ".toml", ".yaml", ".yml", ".json",
            ".md", ".sql", ".sh", ".ps1", ".bat",
            ".html", ".css", ".scss",
        ],
        "exclude_patterns": [
            ".git/**", "node_modules/**", "__pycache__/**",
            "*.pyc", "*.min.js", "*.min.css", "*.lock",
            "dist/**", "build/**", ".venv/**", "venv/**",
            "obj/**", "bin/**", "target/**", "out/**",
        ],
        "max_file_size_kb": 500,
        "skip_binary_files": True,
    },
    "pdf": {
        "page_size": "A4",
        "code_font": "Courier New, Courier, monospace",
        "code_font_size_pt": 9,
        "syntax_theme": "friendly",
        "line_numbers": True,
        "page_numbers": True,
    },
    "toc": {
        "title": "Table of Contents",
    },
}


def _merge(defaults: dict, overrides: dict) -> dict:
    result = dict(defaults)
    for k, v in overrides.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _merge(result[k], v)
        else:
            result[k] = v
    return result


def load_config(config_path: Path, overrides: dict | None = None) -> Config:
    if config_path.exists():
        with open(config_path, "rb") as f:
            raw = tomllib.load(f)
    else:
        raw = {}

    merged = _merge(_DEFAULTS, raw)
    if overrides:
        merged = _merge(merged, overrides)

    p = merged["project"]
    root = Path(p["root"])
    if not root.is_absolute():
        root = (config_path.parent / root).resolve()

    exts = [e.lower() if e.startswith(".") else f".{e.lower()}"
            for e in merged["files"]["include_extensions"]]

    return Config(
        project=ProjectConfig(root=root, output=p["output"]),
        files=FilesConfig(
            include_extensions=exts,
            exclude_patterns=merged["files"]["exclude_patterns"],
            max_file_size_kb=merged["files"]["max_file_size_kb"],
            skip_binary_files=merged["files"]["skip_binary_files"],
        ),
        pdf=PdfConfig(
            page_size=merged["pdf"]["page_size"],
            code_font=merged["pdf"]["code_font"],
            code_font_size_pt=merged["pdf"]["code_font_size_pt"],
            syntax_theme=merged["pdf"]["syntax_theme"],
            line_numbers=merged["pdf"]["line_numbers"],
            page_numbers=merged["pdf"]["page_numbers"],
        ),
        toc=TocConfig(title=merged["toc"]["title"]),
    )

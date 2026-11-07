#!/usr/bin/env python3
"""Render source-code line ranges as deterministic VS Code-inspired PNGs."""

from __future__ import annotations

import argparse
import hashlib
import html
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path
from typing import Iterable


VERSION = "0.1.0"
THEMES = {
    "vscode-dark": {
        "background": "#1e1e1e",
        "foreground": "#d4d4d4",
        "gutter": "#6e7681",
        "gutter_border": "#333333",
        "comment": "#6a9955",
        "string": "#ce9178",
        "keyword": "#569cd6",
        "number": "#b5cea8",
        "function": "#dcdcaa",
        "type": "#4ec9b0",
        "builtin": "#4fc1ff",
        "operator": "#d4d4d4",
    },
    "paper": {
        "background": "#ffffff",
        "foreground": "#24292f",
        "gutter": "#8c959f",
        "gutter_border": "#d0d7de",
        "comment": "#6e7781",
        "string": "#0a3069",
        "keyword": "#cf222e",
        "number": "#0550ae",
        "function": "#8250df",
        "type": "#953800",
        "builtin": "#0550ae",
        "operator": "#24292f",
    },
}


def parse_range(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"\s*(\d+)\s*[-:]\s*(\d+)\s*", value)
    if not match:
        raise argparse.ArgumentTypeError("use START-END, for example 454-466")
    start, end = map(int, match.groups())
    if start < 1 or end < start:
        raise argparse.ArgumentTypeError("line range must satisfy 1 <= START <= END")
    return start, end


def display_columns(line: str, tab_size: int = 4) -> int:
    """Estimate monospace columns, accounting for tabs and wide Unicode glyphs."""
    col = 0
    for char in line:
        if char == "\t":
            col += tab_size - (col % tab_size)
        elif unicodedata.east_asian_width(char) in {"W", "F"}:
            col += 2
        else:
            col += 1
    return col


def token_class(token_type: object) -> str:
    try:
        from pygments.token import Token
    except ImportError:
        return ""
    groups = (
        (Token.Comment, "c"),
        (Token.Literal.String, "s"),
        (Token.Keyword, "k"),
        (Token.Literal.Number, "n"),
        (Token.Name.Function, "f"),
        (Token.Name.Class, "t"),
        (Token.Name.Builtin, "b"),
        (Token.Operator, "o"),
    )
    for parent, css_class in groups:
        if token_type in parent:
            return css_class
    return ""


def highlighted_lines(source: str, filename: str, language: str | None) -> tuple[list[str], bool]:
    """Return escaped, per-line markup. Pygments is optional."""
    try:
        from pygments import lex
        from pygments.lexers import TextLexer, get_lexer_by_name, get_lexer_for_filename
        from pygments.util import ClassNotFound
    except ImportError:
        return [html.escape(line, quote=False) for line in source.split("\n")], False

    try:
        lexer = get_lexer_by_name(language) if language else get_lexer_for_filename(filename)
    except ClassNotFound as exc:
        if language:
            raise ValueError(f"unknown Pygments language {language!r}") from exc
        lexer = TextLexer()

    rows: list[list[str]] = [[]]
    for token_type, value in lex(source, lexer):
        css_class = token_class(token_type)
        parts = value.split("\n")
        for part_index, part in enumerate(parts):
            if part:
                escaped = html.escape(part, quote=False)
                if css_class:
                    rows[-1].append(f'<span class="{css_class}">{escaped}</span>')
                else:
                    rows[-1].append(escaped)
            if part_index < len(parts) - 1:
                rows.append([])
    return ["".join(row) for row in rows], True


def find_browser(explicit: str | None) -> Path:
    if explicit:
        candidate = Path(explicit).expanduser()
        if not candidate.is_file():
            raise FileNotFoundError(f"browser executable not found: {candidate}")
        return candidate.resolve()

    names = ("chrome.exe", "msedge.exe", "chromium.exe", "google-chrome", "chromium")
    for name in names:
        found = shutil.which(name)
        if found:
            return Path(found).resolve()

    if os.name == "nt":
        roots = [
            os.environ.get("PROGRAMFILES"),
            os.environ.get("PROGRAMFILES(X86)"),
            os.environ.get("LOCALAPPDATA"),
        ]
        suffixes = (
            Path("Google/Chrome/Application/chrome.exe"),
            Path("Microsoft/Edge/Application/msedge.exe"),
        )
        for root in filter(None, roots):
            for suffix in suffixes:
                candidate = Path(root) / suffix
                if candidate.is_file():
                    return candidate.resolve()

    raise FileNotFoundError(
        "Chrome, Edge, or Chromium was not found. Pass its path with --browser."
    )


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as file:
        header = file.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError("browser did not produce a valid PNG")
    return struct.unpack(">II", header[16:24])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Make line-numbered, VS Code-inspired source-code PNGs with headless Chrome/Edge."
    )
    parser.add_argument("source", type=Path, help="UTF-8 source file")
    parser.add_argument("--range", type=parse_range, help="inclusive line range, e.g. 454-466")
    parser.add_argument("--output-dir", type=Path, default=Path("codeframe-output"))
    parser.add_argument("--browser", help="path to Chrome, Edge, or Chromium executable")
    parser.add_argument("--theme", choices=THEMES, default="vscode-dark")
    parser.add_argument("--language", help="Pygments lexer name; auto-detected by extension by default")
    parser.add_argument("--encoding", default="utf-8-sig", help="source encoding (default: utf-8-sig)")
    parser.add_argument("--font-size", type=float, default=14)
    parser.add_argument("--line-height", type=float, default=1.5)
    parser.add_argument("--padding", type=int, default=12)
    parser.add_argument("--width", type=int, default=1700, help="minimum CSS viewport width")
    parser.add_argument("--scale", type=int, default=2, help="device scale factor")
    parser.add_argument(
        "--long-lines", choices=("expand", "wrap"), default="expand",
        help="expand viewport to keep long lines intact, or wrap them within --width",
    )
    parser.add_argument("--no-line-numbers", action="store_true")
    parser.add_argument("--no-highlight", action="store_true", help="disable optional Pygments highlighting")
    parser.add_argument("--force", action="store_true", help="overwrite existing HTML/PNG outputs")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    source_path = args.source.expanduser()
    if not source_path.is_file():
        parser.error(f"source file not found: {source_path}")
    if args.font_size <= 0 or args.line_height <= 0 or args.width <= 0 or args.scale <= 0:
        parser.error("font size, line height, width, and scale must be positive")
    if args.padding < 0:
        parser.error("padding must not be negative")

    try:
        source_bytes = source_path.read_bytes()
        source_text = source_bytes.decode(args.encoding)
    except (OSError, UnicodeError) as exc:
        parser.error(f"cannot read source: {exc}")
    source_lines = source_text.splitlines()
    if not source_lines:
        source_lines = [""]

    start, end = args.range or (1, len(source_lines))
    if end > len(source_lines):
        parser.error(f"range ends at line {end}, but source has only {len(source_lines)} lines")
    selected = source_lines[start - 1 : end]
    selected_text = "\n".join(selected)
    digest = hashlib.sha256(source_bytes).hexdigest()

    number_width = max(3, len(str(end)))
    gutter_px = number_width * args.font_size * 0.64 + 42 if not args.no_line_numbers else 14
    pad_x = args.padding * 2
    max_columns = max((display_columns(line) for line in selected), default=0)
    estimated_text_px = max_columns * args.font_size * 0.62 + gutter_px + pad_x + 8
    page_width = max(args.width, math.ceil(estimated_text_px)) if args.long_lines == "expand" else args.width

    if args.long_lines == "wrap":
        available_px = max(1, page_width - gutter_px - pad_x - 16)
        columns_per_row = max(1, int(available_px / (args.font_size * 0.62)))
        visual_rows = sum(max(1, math.ceil(display_columns(line) / columns_per_row)) for line in selected)
    else:
        visual_rows = len(selected)
    page_height = math.ceil(visual_rows * args.font_size * args.line_height + pad_x + 6)
    if page_height > 12000:
        parser.error("estimated image is over 12000 CSS pixels tall; select a smaller line range")

    try:
        browser = find_browser(args.browser)
    except FileNotFoundError as exc:
        parser.error(str(exc))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", source_path.stem).strip("._") or "source"
    suffix = f"lines-{start}-{end}"
    html_path = (args.output_dir / f"{stem}-{suffix}.html").resolve()
    png_path = (args.output_dir / f"{stem}-{suffix}.png").resolve()
    if not args.force and (html_path.exists() or png_path.exists()):
        parser.error("output already exists; choose another --output-dir or pass --force")

    try:
        markup, used_pygments = highlighted_lines(
            selected_text, source_path.name, args.language
        ) if not args.no_highlight else (
            [html.escape(line, quote=False) for line in selected], False
        )
    except ValueError as exc:
        parser.error(str(exc))
    # Keep the source line count authoritative if a lexer emits a trailing newline token.
    if len(markup) != len(selected):
        markup = (markup + [""] * len(selected))[: len(selected)]

    palette = THEMES[args.theme]
    body_rows = []
    gutter_width = number_width
    gutter_css_width = max(4, gutter_width * 0.64 * args.font_size + 30) if not args.no_line_numbers else 12
    wrap_css = (
        "white-space:pre-wrap;overflow-wrap:anywhere;word-break:normal;"
        if args.long_lines == "wrap" else "white-space:pre;"
    )
    for offset, rendered in enumerate(markup):
        number = start + offset
        gutter = f'<td class="ln">{number}</td>' if not args.no_line_numbers else '<td class="ln empty"></td>'
        body_rows.append(f'<tr>{gutter}<td class="code"><code>{rendered or "&#8203;"}</code></td></tr>')

    safe_source_name = (
        html.escape(source_path.name, quote=True)
        .replace("--", "- -")
        .replace("\r", " ")
        .replace("\n", " ")
    )
    metadata = f"<!-- source={safe_source_name}; lines={start}-{end}; sha256={digest}; pygments={str(used_pygments).lower()} -->"
    title = html.escape(f"{source_path.name} lines {start}-{end}", quote=True)
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<style>
*{{box-sizing:border-box}} html,body{{margin:0;width:{page_width}px;height:{page_height}px;overflow:hidden}}
body{{background:{palette['background']};color:{palette['foreground']};padding:{args.padding}px;font-family:Consolas,"Cascadia Mono","Courier New",monospace;font-size:{args.font_size}px;line-height:{args.line_height}}}
table{{border-collapse:collapse;table-layout:fixed;width:100%}} td{{vertical-align:top;padding-top:0;padding-bottom:0;line-height:{args.line_height}}}
td.ln{{width:{gutter_css_width:.0f}px;min-width:{gutter_css_width:.0f}px;padding-right:12px;padding-left:8px;color:{palette['gutter']};text-align:right;border-right:1px solid {palette['gutter_border']};user-select:none;white-space:pre}}
td.ln.empty{{width:12px;min-width:12px}} td.code{{padding-left:14px;color:{palette['foreground']};{wrap_css}}} code{{font:inherit;{wrap_css}tab-size:4}}
.c{{color:{palette['comment']}}}.s{{color:{palette['string']}}}.k{{color:{palette['keyword']}}}.n{{color:{palette['number']}}}
.f{{color:{palette['function']}}}.t{{color:{palette['type']}}}.b{{color:{palette['builtin']}}}.o{{color:{palette['operator']}}}
</style></head><body>{metadata}<table role="presentation"><tbody>{''.join(body_rows)}</tbody></table></body></html>"""
    html_path.write_text(document, encoding="utf-8")

    chrome_args = [
        str(browser),
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--disable-background-networking",
        "--disable-extensions",
        "--no-first-run",
        "--no-default-browser-check",
        f"--force-device-scale-factor={args.scale}",
        f"--window-size={page_width},{page_height}",
        f"--screenshot={png_path}",
    ]
    with tempfile.TemporaryDirectory(prefix="codeframe-shot-profile-") as profile:
        chrome_args.append(f"--user-data-dir={profile}")
        chrome_args.append(html_path.as_uri())
        try:
            completed = subprocess.run(chrome_args, capture_output=True, timeout=90)
        except subprocess.TimeoutExpired:
            parser.error("headless browser timed out after 90 seconds")
    if completed.returncode != 0 or not png_path.exists():
        details = (completed.stderr or completed.stdout or b"no browser diagnostic").decode(
            "utf-8", errors="replace"
        ).strip()
        parser.error(f"headless browser failed: {details[-2500:]}")

    pixel_width, pixel_height = png_dimensions(png_path)
    expected = (page_width * args.scale, page_height * args.scale)
    print(f"PNG: {png_path}")
    print(f"HTML: {html_path}")
    print(f"Source range: {source_path.name}:{start}-{end} ({len(selected)} source lines)")
    print(f"Pygments highlighting: {'on' if used_pygments else 'off'}")
    print(f"Viewport: {page_width}x{page_height} CSS px; PNG: {pixel_width}x{pixel_height} px")
    if (pixel_width, pixel_height) != expected:
        print(f"Warning: expected {expected[0]}x{expected[1]} px; check browser scaling or clipping.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

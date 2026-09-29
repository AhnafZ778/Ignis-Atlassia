"""Build docs/winning-plan/FireAtlas_Winning_Plan.pdf from the markdown sources.

Usage: uv run --no-project --with markdown python scripts/build_winning_plan.py
Requires google-chrome (or chromium) on PATH for the PDF step.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs" / "winning-plan"
SRC = PLAN / "src"
HTML_OUT = PLAN / "FireAtlas_Winning_Plan.html"
PDF_OUT = PLAN / "FireAtlas_Winning_Plan.pdf"

CSS = """
@page { size: A4; margin: 16mm 14mm 18mm 14mm; }
body { font-family: "DejaVu Sans", "Liberation Sans", Arial, sans-serif; font-size: 9.6pt;
       line-height: 1.42; color: #1b1f23; }
h1 { font-size: 17pt; color: #8a2d0b; border-bottom: 2px solid #e0632b; padding-bottom: 3px;
     margin-top: 0; page-break-before: always; }
h1:first-of-type { page-break-before: avoid; }
h2 { font-size: 13pt; color: #5a1f08; margin-top: 18px; border-bottom: 1px solid #ddd; }
h3 { font-size: 11pt; color: #222; margin-top: 14px; }
h2, h3 { page-break-after: avoid; }
table { border-collapse: collapse; width: 100%; margin: 6px 0 10px; font-size: 8.4pt;
        page-break-inside: auto; }
tr { page-break-inside: avoid; }
th, td { border: 1px solid #c9ced3; padding: 3px 5px; vertical-align: top; text-align: left; }
th { background: #f3ede9; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 8.2pt; background: #f4f4f4;
       padding: 0 2px; border-radius: 2px; }
pre { background: #f6f8fa; border: 1px solid #d8dde2; border-left: 3px solid #e0632b;
      padding: 7px 9px; white-space: pre-wrap; word-wrap: break-word; font-size: 7.9pt;
      page-break-inside: avoid; }
pre code { background: none; padding: 0; }
blockquote { border-left: 3px solid #e0632b; margin: 8px 0; padding: 4px 10px;
             background: #fdf4ef; }
.toc { border: 1px solid #ddd; padding: 6px 14px; background: #fafafa; font-size: 9pt; }
.toc ul { list-style: none; padding-left: 14px; margin: 2px 0; }
.toc > ul { padding-left: 0; }
hr { border: none; border-top: 1px solid #ddd; margin: 14px 0; }
"""


def demote(md_text: str) -> str:
    return re.sub(r"^(#{1,5}) ", lambda m: "#" + m.group(1) + " ", md_text, flags=re.M)


def widen_list_indents(md_text: str) -> str:
    """Python-Markdown needs 4-space nesting; the sources use 2-space nesting."""
    out, in_fence = [], False
    for line in md_text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        elif not in_fence and line.startswith(" "):
            stripped = line.lstrip(" ")
            line = " " * (2 * (len(line) - len(stripped))) + stripped
        out.append(line)
    return "\n".join(out)


def build_markdown() -> str:
    parts = [p.read_text(encoding="utf-8") for p in sorted(SRC.glob("*.md"))]
    scorecard = (PLAN / "SCORECARD.md").read_text(encoding="utf-8")
    parts.append(
        "# Appendix D — SCORECARD snapshot at build time\n\n"
        "The live version is `docs/winning-plan/SCORECARD.md`; rebuild this PDF to refresh the snapshot.\n\n"
        + demote(scorecard)
    )
    body = widen_list_indents("\n\n".join(parts))
    first_break = body.index("\n## 0.")
    return body[:first_break] + "\n\n[TOC]\n\n" + body[first_break:]


def render_html(md_text: str) -> str:
    converter = markdown.Markdown(
        extensions=["tables", "fenced_code", "toc", "sane_lists", "attr_list"],
        extension_configs={"toc": {"toc_depth": "1-2", "title": "Contents"}},
    )
    body = converter.convert(md_text).replace("[ ] ", "&#9744; ")
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>FireAtlas Winning Plan</title>"
        f"<style>{CSS}</style></head><body>{body}</body></html>"
    )


def find_chrome() -> str:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    sys.exit("No Chrome/Chromium found on PATH; HTML written, PDF skipped.")


def main() -> None:
    HTML_OUT.write_text(render_html(build_markdown()), encoding="utf-8")
    print(f"wrote {HTML_OUT.relative_to(ROOT)}")
    subprocess.run(
        [
            find_chrome(),
            "--headless=new",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={PDF_OUT}",
            HTML_OUT.as_uri(),
        ],
        check=True,
        capture_output=True,
    )
    print(f"wrote {PDF_OUT.relative_to(ROOT)} ({PDF_OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()

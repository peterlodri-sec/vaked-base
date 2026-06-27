#!/usr/bin/env python3
"""Autogen docs from markdown — no LLM, no hand-rolling.

Scans a docs/ directory tree, converts every .md to styled .html,
writes to site/docs/ ready for wrangler deploy.

Usage:
  python3 tools/docs-autogen.py                          # docs/ -> site/docs/
  python3 tools/docs-autogen.py --source docs --output site/docs
  python3 tools/docs-autogen.py --source ../nix-base/docs --output site/docs/nix-base
"""

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import markdown
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.util import ClassNotFound

# ── Theme (Vaked dark, matches site/docs/index.html) ──
THEME_CSS = """
:root{--bg:#08091a;--surface:#101220;--card:#181a2a;--card2:#1e2040;--border:#222440;--text:#c8d0e0;--text2:#6870a0;--accent:#00d4ff;--green:#00e660;--orange:#f0883e;--radius:8px}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,sans-serif;font-size:15px;line-height:1.7}
.wrap{display:flex;max-width:1200px;margin:0 auto;min-height:100vh}
.sidebar{width:240px;padding:2rem 1rem 2rem 2rem;position:sticky;top:0;height:100vh;overflow-y:auto;border-right:1px solid var(--border);flex-shrink:0}
.sidebar h2{font-size:.75rem;color:var(--text2);text-transform:uppercase;letter-spacing:2px;margin-bottom:.5rem;margin-top:1.2rem}
.sidebar a{display:block;padding:.25rem .5rem;color:var(--text2);text-decoration:none;font-size:.82rem;border-radius:4px;margin-bottom:2px}
.sidebar a:hover,.sidebar a.active{color:var(--accent);background:rgba(0,212,255,.06)}
.sidebar .home{color:var(--accent);font-weight:500;margin-bottom:1rem}
.content{flex:1;padding:2rem 3rem;max-width:800px;min-width:0}
h1{font-size:1.8rem;font-weight:300;letter-spacing:2px;margin-bottom:.5rem;color:var(--accent)}
h2{font-size:1.3rem;font-weight:400;margin-top:2rem;margin-bottom:.6rem;color:var(--green);border-bottom:1px solid var(--border);padding-bottom:.3rem}
h3{font-size:1.05rem;font-weight:500;margin-top:1.5rem;margin-bottom:.4rem;color:var(--text)}
p,li{color:var(--text2)}
a{color:var(--accent)}
code{background:var(--card);padding:.1rem .4rem;border-radius:4px;font-size:.85rem;font-family:'SF Mono',Monaco,Consolas,monospace}
pre{background:var(--card2);border:1px solid var(--border);border-radius:var(--radius);padding:1rem;overflow-x:auto;margin:1rem 0}
pre code{background:none;padding:0}
table{border-collapse:collapse;width:100%;margin:1rem 0;font-size:.85rem}
th,td{border:1px solid var(--border);padding:.5rem .8rem;text-align:left}
th{background:var(--card);color:var(--text2)}
blockquote{border-left:3px solid var(--accent);padding:.5rem 1rem;margin:1rem 0;background:var(--card);border-radius:0 var(--radius) var(--radius) 0;color:var(--text2)}
img{max-width:100%;border-radius:var(--radius)}
hr{border:none;border-top:1px solid var(--border);margin:2rem 0}
.footer{margin-top:3rem;padding-top:1rem;border-top:1px solid var(--border);color:var(--text2);font-size:.75rem;display:flex;justify-content:space-between}
.breadcrumb{font-size:.8rem;color:var(--text2);margin-bottom:1rem}
.breadcrumb a{color:var(--text2)} .breadcrumb a:hover{color:var(--accent)}
.tag{display:inline-block;padding:.1rem .5rem;border-radius:4px;font-size:.7rem;background:rgba(0,212,255,.1);color:var(--accent);margin-bottom:.5rem}
""".strip()

# Pygments style — dark, matches Vaked theme
PYGMENTS_CSS = HtmlFormatter(style="material").get_style_defs()


def slugify(text: str) -> str:
    """Turn a heading into a URL-friendly anchor."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", "-", text)
    return text[:80]


def extract_title(md: str) -> tuple[str, str]:
    """Extract title from first h1 or frontmatter. Returns (title, cleaned_md)."""
    # Check for YAML frontmatter
    if md.startswith("---"):
        parts = md.split("---", 2)
        if len(parts) >= 3:
            cleaned = parts[2].strip()
            # Try to find title in frontmatter
            fm = parts[1]
            for line in fm.split("\n"):
                if line.startswith("title:"):
                    title = line.split(":", 1)[1].strip().strip('"').strip("'")
                    return title, cleaned
    # Fallback: first h1
    m = re.search(r"^#\s+(.+)$", md, re.MULTILINE)
    if m:
        return m.group(1).strip(), md
    return "Untitled", md


def parse_markdown(md_text: str) -> str:
    """Convert markdown to HTML with code highlighting."""

    # Process code blocks with pygments
    def _highlight_code(match):
        info = match.group(1) or ""
        code = match.group(2)
        lang = info.strip().split()[0] if info else ""
        if lang:
            try:
                lexer = get_lexer_by_name(lang, stripall=True)
            except ClassNotFound:
                try:
                    lexer = guess_lexer(code)
                except ClassNotFound:
                    lexer = get_lexer_by_name("text")
        else:
            try:
                lexer = guess_lexer(code)
            except ClassNotFound:
                lexer = get_lexer_by_name("text")
        formatter = HtmlFormatter(style="material")
        return highlight(code, lexer, formatter)

    md_text = re.sub(
        r"```(\w*)\n(.*?)```",
        _highlight_code,
        md_text,
        flags=re.DOTALL,
    )

    # Convert to HTML
    html = markdown.markdown(
        md_text,
        extensions=[
            "markdown.extensions.fenced_code",
            "markdown.extensions.tables",
            "markdown.extensions.toc",
            "markdown.extensions.nl2br",
        ],
    )
    return html


def extract_headings(md_text: str) -> list[dict]:
    """Extract h2/h3 headings for sidebar navigation."""
    headings = []
    for line in md_text.split("\n"):
        m = re.match(r"^(#{2,3})\s+(.+)$", line)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            anchor = slugify(text)
            headings.append({"level": level, "text": text, "anchor": anchor})
    return headings


def render_page(title: str, html_body: str, headings: list[dict],
                sidebar_links: list[dict] | None = None,
                source_rel: str = "", breadcrumb: str = "") -> str:
    """Wrap HTML body in a full page with sidebar."""

    # Build sidebar
    sidebar_html = '<div class="sidebar">'
    sidebar_html += '<a href="/docs/" class="home">△ docs</a>'

    if sidebar_links:
        for group in sidebar_links:
            if "label" in group:
                sidebar_html += f"<h2>{group['label']}</h2>"
            for item in group.get("items", []):
                cls = ' active' if item.get("active") else ''
                sidebar_html += f'<a href="{item["href"]}" class="{cls}">{item["label"]}</a>'

    # Add table of contents from headings
    if headings:
        sidebar_html += "<h2>On this page</h2>"
        for h in headings:
            indent = "  " if h["level"] == 3 else ""
            sidebar_html += f'<a href="#{h["anchor"]}" style="padding-left:{1 if h["level"]==3 else 0.5}rem">{indent}{h["text"]}</a>'

    sidebar_html += "</div>"

    # Breadcrumb
    bc_html = ""
    if breadcrumb:
        bc_html = f'<div class="breadcrumb">{breadcrumb}</div>'

    source_html = ""
    if source_rel:
        gh_url = f"https://github.com/peterlodri-sec/vaked-base/blob/main/{source_rel}"
        source_html = f'<a href="{gh_url}" style="color:var(--text2);font-size:.78rem">View source →</a>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title} — Vaked Docs</title>
<style>{THEME_CSS}</style>
<style>{PYGMENTS_CSS}</style>
</head>
<body>
<div class="wrap">
{sidebar_html}
<div class="content">
{bc_html}
<h1>{title}</h1>
{html_body}
<div class="footer">
<span>{source_html}</span>
<span>Genesis seal <code style="font-size:.7rem">7c242080</code></span>
</div>
</div>
</div>
</body>
</html>"""


def build_sidebar(repo_name: str, current_path: str,
                  all_files: list[dict]) -> list[dict]:
    """Build sidebar link groups from discovered files."""
    groups = []
    # Group by top-level directory
    dirs = {}
    for f in all_files:
        parts = f["relpath"].split("/")
        top = parts[0] if len(parts) > 1 else "."
        dirs.setdefault(top, []).append(f)

    for top in sorted(dirs.keys()):
        label = top if top != "." else repo_name
        items = []
        for f in dirs[top]:
            active = f["relpath"] == current_path
            items.append({
                "label": f["title"],
                "href": f["url"],
                "active": active,
            })
        groups.append({"label": label.capitalize(), "items": items})
    return groups


def walk_and_generate(source_dir: str, output_dir: str,
                      repo_name: str = "vaked-base",
                      prefix: str = "") -> list[dict]:
    """Walk source_dir, convert .md to .html, write to output_dir."""
    src = Path(source_dir)
    dst = Path(output_dir)
    dst.mkdir(parents=True, exist_ok=True)

    generated_files = []

    for md_file in sorted(src.rglob("*.md")):
        rel = md_file.relative_to(src)
        text = md_file.read_text(encoding="utf-8")

        title, cleaned_md = extract_title(text)
        headings = extract_headings(cleaned_md)
        html_body = parse_markdown(cleaned_md)

        # Output path: replace .md with .html
        out_name = rel.with_suffix(".html")
        out_path = dst / out_name
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # URL for the generated page
        # Cloudflare Pages strips .html extension — use clean URLs
        clean_name = out_name.with_suffix("") if out_name.suffix == ".html" else out_name
        url = f"/docs/{prefix}{clean_name}" if prefix else f"/docs/{clean_name}"

        # Source relative path for GitHub link
        source_rel = str(Path(source_dir) / rel)

        # Breadcrumb
        parts = rel.parts[:-1]
        bc_parts = ['<a href="/docs/">Docs</a>']
        for i, part in enumerate(parts):
            href = "/".join(["/docs", prefix] if prefix else ["/docs"] + list(parts[:i+1]))
            bc_parts.append(f'<a href="{href}/">{part}</a>')
        bc_parts.append(rel.stem)
        breadcrumb = " / ".join(bc_parts)

        page = render_page(
            title=title,
            html_body=html_body,
            headings=headings,
            source_rel=source_rel,
            breadcrumb=breadcrumb,
        )

        out_path.write_text(page, encoding="utf-8")
        print(f"  ✓ {rel} → {out_name}")
        generated_files.append({
            "relpath": str(rel),
            "title": title,
            "url": url,
        })

    return generated_files


def main():
    parser = argparse.ArgumentParser(description="Autogen docs from markdown")
    parser.add_argument("--source", default="docs",
                        help="Source markdown directory (default: docs/)")
    parser.add_argument("--output", default="site/docs",
                        help="Output HTML directory (default: site/docs/)")
    parser.add_argument("--repo", default="vaked-base",
                        help="Repo name for sidebar")
    parser.add_argument("--prefix", default="",
                        help="URL prefix for docs (e.g. 'vaked/')")
    args = parser.parse_args()

    src_dir = os.path.abspath(args.source)
    out_dir = os.path.abspath(args.output)

    if not os.path.isdir(src_dir):
        print(f"Source directory not found: {src_dir}")
        sys.exit(1)

    print(f"Autogen docs: {src_dir} → {out_dir}")
    print(f"  Repo: {args.repo}, Prefix: /docs/{args.prefix}")

    generated = walk_and_generate(src_dir, out_dir, args.repo, args.prefix)
    print(f"\nDone. {len(generated)} files generated.")
    return generated


if __name__ == "__main__":
    main()

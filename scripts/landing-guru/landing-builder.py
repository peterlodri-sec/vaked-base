#!/usr/bin/env python3
"""
Landing Page Builder for Vaked documentation site.

Reads landing cache JSON files (.landing-cache/*.json) and renders HTML pages:
- docs/website/index.html (hero + landing + example showcase)
- docs/website/examples.html (full example catalog)
- docs/website/docs.html (doc site map + reading order)
- docs/website/og-image.svg (open-graph preview)
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import html

# ANSI color codes
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"


@dataclass
class LandingConfig:
    """Configuration loaded from .landing-cache files."""
    repo_root: Path
    cache_dir: Path
    output_dir: Path
    examples_catalog: Optional[Dict[str, Any]] = None
    coherence_graph: Optional[Dict[str, Any]] = None
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class LandingBuilder:
    """Main landing page builder engine."""

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = repo_root or Path(__file__).parent.parent.parent
        self.cache_dir = self.repo_root / ".landing-cache"
        self.output_dir = self.repo_root / "docs" / "website"
        self.config = LandingConfig(
            repo_root=self.repo_root,
            cache_dir=self.cache_dir,
            output_dir=self.output_dir,
        )

    def ensure_dirs(self) -> None:
        """Create output directories if they don't exist."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def load_cache_files(self) -> bool:
        """Load JSON files from .landing-cache directory."""
        if not self.cache_dir.exists():
            self.config.errors.append(
                f"Cache directory not found: {self.cache_dir}"
            )
            return False

        try:
            # Load examples catalog
            examples_file = self.cache_dir / "examples-catalog.json"
            if examples_file.exists():
                with open(examples_file, "r") as f:
                    self.config.examples_catalog = json.load(f)
            else:
                self.config.examples_catalog = {"examples": []}

            # Load coherence graph
            coherence_file = self.cache_dir / "coherence-graph.json"
            if coherence_file.exists():
                with open(coherence_file, "r") as f:
                    self.config.coherence_graph = json.load(f)
            else:
                self.config.coherence_graph = {"docs": [], "relationships": []}

            return True
        except json.JSONDecodeError as e:
            self.config.errors.append(f"JSON decode error: {e}")
            return False
        except Exception as e:
            self.config.errors.append(f"Load error: {e}")
            return False

    def _html_escape(self, text: str) -> str:
        """HTML-escape a string."""
        return html.escape(str(text)) if text else ""

    def _build_index_html(self) -> str:
        """Build the main landing/index page."""
        examples = self.config.examples_catalog.get("examples", [])[:6]
        example_rows = "\n".join(
            self._build_example_card(ex) for ex in examples
        )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vaked — Capability-Graph Language</title>
    <meta name="description" content="Vaked: a flake-native capability-graph language for declaring, materializing, and enforcing infrastructure.">
    <meta property="og:title" content="Vaked — Capability-Graph Language">
    <meta property="og:description" content="Declare capability graphs. Nix materializes. OTP supervises. Zig enforces. eBPF testifies.">
    <meta property="og:image" content="/docs/website/og-image.svg">
    <meta property="og:type" content="website">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #fafafa;
        }}

        header {{
            background: linear-gradient(135deg, #1a237e 0%, #283593 100%);
            color: white;
            padding: 4rem 2rem;
            text-align: center;
        }}

        header h1 {{
            font-size: 3rem;
            margin-bottom: 1rem;
        }}

        header p {{
            font-size: 1.2rem;
            opacity: 0.9;
            max-width: 600px;
            margin: 0 auto;
        }}

        nav {{
            background: #f5f5f5;
            padding: 1rem;
            display: flex;
            justify-content: center;
            gap: 2rem;
            border-bottom: 1px solid #ddd;
        }}

        nav a {{
            color: #1a237e;
            text-decoration: none;
            font-weight: 500;
        }}

        nav a:hover {{
            text-decoration: underline;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
        }}

        section {{
            margin: 3rem 0;
        }}

        section h2 {{
            font-size: 2rem;
            margin-bottom: 1.5rem;
            color: #1a237e;
        }}

        .examples-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1.5rem;
        }}

        .example-card {{
            background: white;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 1.5rem;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            transition: box-shadow 0.2s;
        }}

        .example-card:hover {{
            box-shadow: 0 4px 8px rgba(0,0,0,0.15);
        }}

        .example-card h3 {{
            font-size: 1.2rem;
            margin-bottom: 0.5rem;
            color: #1a237e;
        }}

        .example-card p {{
            font-size: 0.95rem;
            color: #666;
            margin-bottom: 1rem;
        }}

        .example-card .tags {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
        }}

        .tag {{
            display: inline-block;
            background: #e3f2fd;
            color: #1976d2;
            padding: 0.25rem 0.75rem;
            border-radius: 16px;
            font-size: 0.85rem;
        }}

        .cta-link {{
            display: inline-block;
            color: #1976d2;
            text-decoration: none;
            font-weight: 500;
            margin-top: 1rem;
        }}

        .cta-link:hover {{
            text-decoration: underline;
        }}

        footer {{
            background: #f5f5f5;
            border-top: 1px solid #ddd;
            padding: 2rem;
            text-align: center;
            color: #666;
            margin-top: 4rem;
        }}
    </style>
</head>
<body>
    <header>
        <h1>Vaked</h1>
        <p>A capability-graph language for declaring, materializing, and enforcing infrastructure.</p>
        <p style="font-size: 1rem; margin-top: 1rem;">
            Vaked declares. Nix materializes. OTP supervises. Zig enforces. eBPF testifies.
        </p>
    </header>

    <nav>
        <a href="/">Home</a>
        <a href="/examples.html">Examples</a>
        <a href="/docs.html">Documentation</a>
        <a href="https://github.com/vaked-lang/vaked" target="_blank">GitHub</a>
    </nav>

    <div class="container">
        <section id="intro">
            <h2>What is Vaked?</h2>
            <p>
                Vaked is a flake-native capability-graph language that enables you to:
            </p>
            <ul style="margin: 1rem 0 0 2rem;">
                <li>Declare security policies and capability graphs in a typed, composable syntax</li>
                <li>Materialize to Nix, NixOS modules, and provenance artifacts</li>
                <li>Enforce at runtime via OTP supervision, Zig daemons, and eBPF policies</li>
                <li>Verify separation of duties and privilege attenuation at compile time</li>
            </ul>
        </section>

        <section id="examples">
            <h2>Featured Examples</h2>
            <div class="examples-grid">
{example_rows}
            </div>
            <p>
                <a href="/examples.html" class="cta-link">→ View all examples</a>
            </p>
        </section>

        <section id="docs">
            <h2>Learn More</h2>
            <p>
                Start with the <a href="/docs.html">documentation site map</a> or read the
                <a href="https://github.com/vaked-lang/vaked/blob/main/docs/context/PROJECT_CONTEXT.md">
                    project overview
                </a>.
            </p>
        </section>
    </div>

    <footer>
        <p>Vaked — Capability-Graph Language</p>
        <p style="font-size: 0.9rem; margin-top: 0.5rem;">
            Generated {datetime.utcnow().isoformat()}Z
        </p>
    </footer>
</body>
</html>"""

    def _build_example_card(self, example: Dict[str, Any]) -> str:
        """Build a single example card for the grid."""
        title = self._html_escape(example.get("name", "Untitled"))
        description = self._html_escape(example.get("description", ""))
        tags = example.get("tags", [])
        filepath = example.get("filepath", "")

        tags_html = "\n".join(
            f'<span class="tag">{self._html_escape(tag)}</span>'
            for tag in tags[:3]
        )

        return f"""        <div class="example-card">
            <h3>{title}</h3>
            <p>{description}</p>
            <div class="tags">
{tags_html}
            </div>
            <a href="{self._html_escape(filepath)}" class="cta-link">View →</a>
        </div>"""

    def _build_examples_html(self) -> str:
        """Build the full examples catalog page."""
        examples = self.config.examples_catalog.get("examples", [])
        example_rows = "\n".join(
            self._build_example_card(ex) for ex in examples
        )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Examples — Vaked</title>
    <meta name="description" content="Vaked example catalog: supply-chain, scalability, type system, and more.">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #fafafa;
        }}

        header {{
            background: linear-gradient(135deg, #1a237e 0%, #283593 100%);
            color: white;
            padding: 2rem;
            text-align: center;
        }}

        header h1 {{
            font-size: 2rem;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
        }}

        .examples-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 1.5rem;
            margin: 2rem 0;
        }}

        .example-card {{
            background: white;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 1.5rem;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}

        .example-card h3 {{
            color: #1a237e;
            margin-bottom: 0.5rem;
        }}

        .tag {{
            display: inline-block;
            background: #e3f2fd;
            color: #1976d2;
            padding: 0.25rem 0.75rem;
            border-radius: 16px;
            font-size: 0.85rem;
            margin-right: 0.5rem;
        }}

        footer {{
            background: #f5f5f5;
            padding: 2rem;
            text-align: center;
            margin-top: 4rem;
            border-top: 1px solid #ddd;
        }}
    </style>
</head>
<body>
    <header>
        <h1>Vaked Examples</h1>
        <p>Explore capability-graph patterns and use cases</p>
    </header>

    <div class="container">
        <p>Total examples: <strong>{len(examples)}</strong></p>

        <div class="examples-grid">
{example_rows}
        </div>
    </div>

    <footer>
        <p><a href="/">← Back to home</a></p>
        <p style="font-size: 0.9rem; margin-top: 0.5rem;">
            Generated {datetime.utcnow().isoformat()}Z
        </p>
    </footer>
</body>
</html>"""

    def _build_docs_html(self) -> str:
        """Build the documentation site map page."""
        docs = self.config.coherence_graph.get("docs", [])

        doc_rows = "\n".join(
            f"""        <li>
            <strong>{self._html_escape(doc.get('title', doc.get('id', 'Unknown')))}</strong>
            <p>{self._html_escape(doc.get('description', ''))}</p>
        </li>"""
            for doc in docs
        )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Documentation — Vaked</title>
    <meta name="description" content="Vaked documentation: language design, type system, runtime architecture.">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #fafafa;
        }}

        header {{
            background: linear-gradient(135deg, #1a237e 0%, #283593 100%);
            color: white;
            padding: 2rem;
            text-align: center;
        }}

        header h1 {{
            font-size: 2rem;
        }}

        .container {{
            max-width: 900px;
            margin: 0 auto;
            padding: 2rem;
        }}

        ol {{
            list-style: decimal;
            margin: 2rem 0;
        }}

        ol li {{
            margin: 1.5rem 0;
            margin-left: 2rem;
            background: white;
            padding: 1rem;
            border-left: 4px solid #1976d2;
            border-radius: 4px;
        }}

        ol li strong {{
            display: block;
            color: #1a237e;
            margin-bottom: 0.5rem;
        }}

        ol li p {{
            color: #666;
            font-size: 0.95rem;
        }}

        footer {{
            background: #f5f5f5;
            padding: 2rem;
            text-align: center;
            margin-top: 4rem;
            border-top: 1px solid #ddd;
        }}
    </style>
</head>
<body>
    <header>
        <h1>Vaked Documentation</h1>
        <p>Learning path and reference guides</p>
    </header>

    <div class="container">
        <h2>Reading Order</h2>
        <ol>
{doc_rows}
        </ol>
    </div>

    <footer>
        <p><a href="/">← Back to home</a></p>
        <p style="font-size: 0.9rem; margin-top: 0.5rem;">
            Generated {datetime.utcnow().isoformat()}Z
        </p>
    </footer>
</body>
</html>"""

    def _build_og_image_svg(self) -> str:
        """Build the open-graph preview image (SVG)."""
        return """<?xml version="1.0" encoding="UTF-8"?>
<svg width="1200" height="630" viewBox="0 0 1200 630" xmlns="http://www.w3.org/2000/svg">
    <!-- Background -->
    <defs>
        <linearGradient id="grad1" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" style="stop-color:#1a237e;stop-opacity:1" />
            <stop offset="100%" style="stop-color:#283593;stop-opacity:1" />
        </linearGradient>
    </defs>

    <rect width="1200" height="630" fill="url(#grad1)"/>

    <!-- Title -->
    <text x="600" y="200" font-size="80" font-weight="bold" fill="white" text-anchor="middle" font-family="Arial, sans-serif">
        Vaked
    </text>

    <!-- Subtitle -->
    <text x="600" y="280" font-size="32" fill="white" text-anchor="middle" font-family="Arial, sans-serif" opacity="0.9">
        Capability-Graph Language
    </text>

    <!-- Tagline -->
    <text x="600" y="350" font-size="24" fill="white" text-anchor="middle" font-family="Arial, sans-serif" opacity="0.8">
        Declare. Materialize. Enforce.
    </text>

    <!-- Graph visualization (simple) -->
    <circle cx="300" cy="450" r="40" fill="#81c784" opacity="0.7"/>
    <circle cx="600" cy="450" r="40" fill="#64b5f6" opacity="0.7"/>
    <circle cx="900" cy="450" r="40" fill="#ffb74d" opacity="0.7"/>

    <!-- Connecting lines -->
    <line x1="340" y1="450" x2="560" y2="450" stroke="white" stroke-width="2" opacity="0.5"/>
    <line x1="640" y1="450" x2="860" y2="450" stroke="white" stroke-width="2" opacity="0.5"/>

    <!-- Footer text -->
    <text x="600" y="590" font-size="18" fill="white" text-anchor="middle" font-family="Arial, sans-serif" opacity="0.6">
        vaked-lang.org
    </text>
</svg>"""

    def write_pages(self) -> bool:
        """Write all generated HTML pages to disk."""
        pages = {
            "index.html": self._build_index_html(),
            "examples.html": self._build_examples_html(),
            "docs.html": self._build_docs_html(),
            "og-image.svg": self._build_og_image_svg(),
        }

        for filename, content in pages.items():
            try:
                filepath = self.output_dir / filename
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"{GREEN}✓{RESET} {filepath.relative_to(self.repo_root)}")
            except Exception as e:
                self.config.errors.append(f"{filename}: {e}")
                return False

        return True

    def run(self, verbose: bool = False) -> int:
        """Run the full landing builder pipeline."""
        print(f"\n{BOLD}Landing Builder — Website Pages{RESET}\n")

        # Ensure output directories
        self.ensure_dirs()

        # Load cache files
        print(f"{BLUE}[→] Loading cache files...{RESET}")
        if not self.load_cache_files():
            print(f"{YELLOW}[!] Cache load failed{RESET}")
            for error in self.config.errors:
                print(f"  {error}")
            return 1

        examples_count = len(self.config.examples_catalog.get("examples", []))
        docs_count = len(self.config.coherence_graph.get("docs", []))
        print(
            f"{GREEN}✓ Loaded {examples_count} examples, {docs_count} docs{RESET}\n"
        )

        # Generate and write pages
        print(f"{BLUE}[→] Generating HTML pages...{RESET}")
        if not self.write_pages():
            print(f"{YELLOW}[!] Page generation failed{RESET}")
            for error in self.config.errors:
                print(f"  {error}")
            return 1

        print(f"\n{GREEN}✓ Pages generated in {self.output_dir}{RESET}\n")

        # Show errors if any
        if self.config.errors:
            print(f"{YELLOW}[!] {len(self.config.errors)} warning(s):{RESET}")
            for error in self.config.errors[:5]:
                print(f"  {error}")
            if len(self.config.errors) > 5:
                print(f"  ... and {len(self.config.errors) - 5} more")

        return 0


def main():
    """Entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Build landing pages from cache JSON files"
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (auto-detected if not provided)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    builder = LandingBuilder(repo_root=args.repo_root)
    return builder.run(verbose=args.verbose)


if __name__ == "__main__":
    sys.exit(main())

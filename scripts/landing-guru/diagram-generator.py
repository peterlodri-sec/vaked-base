#!/usr/bin/env python3
"""
Diagram Generator for landing page assets.

Scans Markdown and EBNF files for architecture, flow, pipeline, and graph mentions.
Generates D2 diagram sources, auto-renders to SVG if d2 CLI is available.
"""

import re
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

# ANSI color codes
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"

@dataclass
class DiagramSpec:
    """Represents a diagram specification extracted from source."""
    name: str
    source_file: str
    line_number: int
    trigger_keyword: str
    context: str
    d2_source: str
    output_d2: str
    output_svg: str

class DiagramGenerator:
    """Main diagram generation engine."""

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = repo_root or Path(__file__).parent.parent.parent
        self.docs_root = self.repo_root / "docs"
        self.assets_dir = self.docs_root / "assets"
        self.diagrams_dir = self.assets_dir / "diagrams"
        self.results: List[DiagramSpec] = []
        self.errors: List[Tuple[str, str]] = []

    def ensure_dirs(self) -> None:
        """Create output directories if they don't exist."""
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.diagrams_dir.mkdir(parents=True, exist_ok=True)

    def scan_file(self, filepath: Path) -> None:
        """Scan a single file for diagram triggers."""
        if not filepath.exists():
            self.errors.append((str(filepath), "File not found"))
            return

        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception as e:
            self.errors.append((str(filepath), f"Read error: {e}"))
            return

        # Keywords that trigger diagram generation
        keywords = ["architecture", "flow", "pipeline", "graph"]
        keyword_pattern = re.compile(
            r"\b(" + "|".join(keywords) + r")\b",
            re.IGNORECASE
        )

        for i, line in enumerate(lines, start=1):
            if keyword_pattern.search(line):
                # Extract context: preceding and following lines
                start = max(0, i - 2)
                end = min(len(lines), i + 3)
                context = "".join(lines[start:end]).strip()

                match = keyword_pattern.search(line)
                keyword = match.group(1).lower()

                # Generate diagram name from file + line
                base_name = filepath.stem.lower()
                diagram_name = f"{base_name}-{keyword}-line{i}"

                # Create D2 source based on keyword and context
                d2_source = self._generate_d2(keyword, context, filepath, i)

                spec = DiagramSpec(
                    name=diagram_name,
                    source_file=str(filepath.relative_to(self.repo_root)),
                    line_number=i,
                    trigger_keyword=keyword,
                    context=context[:200],  # Truncate for readability
                    d2_source=d2_source,
                    output_d2=str(self.diagrams_dir / f"{diagram_name}.d2"),
                    output_svg=str(self.diagrams_dir / f"{diagram_name}.svg"),
                )
                self.results.append(spec)

    def _generate_d2(
        self,
        keyword: str,
        context: str,
        source_file: Path,
        line_num: int
    ) -> str:
        """Generate D2 source code based on keyword and context."""

        # Base template for different diagram types
        if keyword == "architecture":
            return self._d2_architecture_template(context)
        elif keyword == "flow":
            return self._d2_flow_template(context)
        elif keyword == "pipeline":
            return self._d2_pipeline_template(context)
        elif keyword == "graph":
            return self._d2_graph_template(context)
        else:
            return self._d2_generic_template(keyword, context)

    def _d2_architecture_template(self, context: str) -> str:
        """Generate D2 for architecture diagrams."""
        return """# Auto-generated architecture diagram
direction: down

Declaration: {
  shape: box
  style.fill: "#e1f5ff"
}

Materialization: {
  shape: box
  style.fill: "#fff3e0"
}

Enforcement: {
  shape: box
  style.fill: "#f3e5f5"
}

Declaration -> Materialization: "compile & transform"
Materialization -> Enforcement: "deploy & execute"

notes: {
  style.text-transform: uppercase
  shape: note
  "Auto-generated from source scan\\nUpdate context in source file to refine"
}"""

    def _d2_flow_template(self, context: str) -> str:
        """Generate D2 for flow diagrams."""
        return """# Auto-generated flow diagram
direction: right

Input: {
  shape: circle
  style.fill: "#c8e6c9"
}

Process: {
  shape: square
  style.fill: "#bbdefb"
}

Output: {
  shape: circle
  style.fill: "#ffccbc"
}

Input -> Process: "transform"
Process -> Output: "emit"

notes: {
  style.text-transform: uppercase
  shape: note
  "Auto-generated flow\\nEnrich with real stages in source"
}"""

    def _d2_pipeline_template(self, context: str) -> str:
        """Generate D2 for pipeline diagrams."""
        return """# Auto-generated pipeline diagram
direction: right

Parse: {
  shape: box
  style.fill: "#e3f2fd"
}

Check: {
  shape: box
  style.fill: "#e8f5e9"
}

Lower: {
  shape: box
  style.fill: "#fff3e0"
}

Emit: {
  shape: box
  style.fill: "#f3e5f5"
}

Parse -> Check: "AST"
Check -> Lower: "Typed IR"
Lower -> Emit: "Artifacts"

legend: {
  shape: note
  "Compilation pipeline\\nAuto-generated; refine source context"
}"""

    def _d2_graph_template(self, context: str) -> str:
        """Generate D2 for graph diagrams."""
        return """# Auto-generated graph diagram

A: {
  shape: circle
  style.fill: "#bbdefb"
}

B: {
  shape: circle
  style.fill: "#c8e6c9"
}

C: {
  shape: circle
  style.fill: "#ffccbc"
}

A -> B: "edge AB"
B -> C: "edge BC"
A -> C: "edge AC"

key: {
  shape: note
  "Capability/dependency graph\\nAuto-generated; add details in source"
}"""

    def _d2_generic_template(self, keyword: str, context: str) -> str:
        """Generic D2 template for unrecognized keywords."""
        return f"""# Auto-generated diagram for '{keyword}'
direction: down

Source: {{
  shape: box
  style.fill: "#ede7f6"
}}

Process: {{
  shape: diamond
  style.fill: "#f3e5f5"
}}

Output: {{
  shape: box
  style.fill: "#e1bee7"
}}

Source -> Process: "transform"
Process -> Output: "result"

note: {{
  shape: note
  "Generic template for keyword: {keyword}\\nCustomize in diagram-generator.py"
}}"""

    def write_diagrams(self) -> None:
        """Write D2 sources to disk."""
        for spec in self.results:
            try:
                output_path = Path(spec.output_d2)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "w") as f:
                    f.write(spec.d2_source)
            except Exception as e:
                self.errors.append((spec.output_d2, f"Write error: {e}"))

    def render_diagrams(self, check_cli: bool = True) -> bool:
        """Render D2 sources to SVG using d2 CLI."""
        if not check_cli:
            return False

        # Check if d2 is available
        try:
            subprocess.run(["d2", "--version"], capture_output=True, check=True)
            d2_available = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            d2_available = False

        if not d2_available:
            print(
                f"{YELLOW}[!] d2 CLI not found; skipping SVG render{RESET}"
            )
            return False

        rendered = 0
        for spec in self.results:
            try:
                cmd = [
                    "d2",
                    "--layout=elk",
                    spec.output_d2,
                    spec.output_svg,
                ]
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    rendered += 1
                else:
                    self.errors.append(
                        (spec.output_svg,
                         f"d2 render failed: {result.stderr}")
                    )
            except subprocess.TimeoutExpired:
                self.errors.append((spec.output_svg, "d2 render timeout"))
            except Exception as e:
                self.errors.append((spec.output_svg, f"Render error: {e}"))

        print(
            f"{GREEN}✓ Rendered {rendered}/{len(self.results)} diagrams to SVG{RESET}"
        )
        return rendered > 0

    def collect_markdown_files(self) -> List[Path]:
        """Collect all .md and .ebnf files to scan."""
        files = []
        for ext in ["*.md", "*.ebnf"]:
            files.extend(self.docs_root.rglob(ext))
        return files

    def generate_report(self) -> Dict:
        """Generate a JSON report of all diagrams and errors."""
        return {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "diagrams_generated": len(self.results),
            "errors": len(self.errors),
            "diagrams": [asdict(spec) for spec in self.results],
            "errors_list": [{"file": f, "error": e} for f, e in self.errors],
        }

    def run(self, verbose: bool = False) -> int:
        """Run the full pipeline."""
        print(f"\n{BOLD}Diagram Generator — Landing Assets{RESET}\n")

        # Ensure output directories
        self.ensure_dirs()

        # Collect files to scan
        files = self.collect_markdown_files()
        print(
            f"{BLUE}[→] Scanning {len(files)} files for diagram triggers...{RESET}"
        )

        for filepath in files:
            if verbose:
                print(f"  {filepath.relative_to(self.repo_root)}")
            self.scan_file(filepath)

        if not self.results:
            print(f"{YELLOW}[!] No diagrams found{RESET}")
            return 0

        print(
            f"{GREEN}✓ Found {len(self.results)} diagram(s){RESET}\n"
        )

        # Write D2 sources
        print(f"{BLUE}[→] Writing D2 sources...{RESET}")
        self.write_diagrams()
        print(
            f"{GREEN}✓ Wrote {len(self.results)} D2 files to {self.diagrams_dir}{RESET}\n"
        )

        # Try to render to SVG
        print(f"{BLUE}[→] Rendering to SVG...{RESET}")
        self.render_diagrams()

        # Write report
        report_file = self.diagrams_dir / ".diagram-report.json"
        report = self.generate_report()
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)

        print(f"\n{BLUE}Report: {report_file}{RESET}\n")

        # Show errors
        if self.errors:
            print(f"{YELLOW}[!] {len(self.errors)} error(s):{RESET}")
            for filepath, error in self.errors[:5]:
                print(f"  {filepath}: {error}")
            if len(self.errors) > 5:
                print(f"  ... and {len(self.errors) - 5} more")
            print()

        return 0 if not self.errors else 1


def main():
    """Entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate D2 diagrams from markdown/EBNF mentions"
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
    parser.add_argument(
        "--no-render",
        action="store_true",
        help="Skip SVG rendering; write D2 sources only",
    )

    args = parser.parse_args()

    gen = DiagramGenerator(repo_root=args.repo_root)
    gen.run(verbose=args.verbose)

    if not args.no_render:
        gen.render_diagrams(check_cli=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())

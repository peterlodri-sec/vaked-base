#!/usr/bin/env python3
"""
Generate images for Vaked paper and documentation via OpenRouter API.

Usage:
  OPENROUTER_API_KEY="your-key" python3 generate_images.py [--list] [--all] [--image NAME]

Requires:
  - OPENROUTER_API_KEY environment variable
  - requests library: pip install requests
"""

import os
import sys
import json
import base64
from pathlib import Path
import requests

OPENROUTER_API_URL = "https://api.openrouter.ai/api/v1/images/generations"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Image generation specs with prompts and metadata
IMAGES = {
    "vaked-logo": {
        "prompt": "Professional logo for 'Vaked', a capability-graph programming language. Design should incorporate: graph topology, capability flow, and security/trust symbolism. Minimalist, modern, suitable for academic paper and GitHub. Color: deep blue and silver. Style: geometric, clean lines.",
        "alt_text": "Vaked logo: geometric graph topology representing capability flows",
        "size": "1024x1024",
        "output": "docs/images/vaked-logo.png",
    },
    "architecture-diagram": {
        "prompt": "System architecture diagram for Vaked: Three-layer stack showing: (1) Declaration layer (Vaked code), (2) Materialization layer (Nix/flake.lock), (3) Enforcement layer (Zig daemons + eBPF). Arrows show data flow from top to bottom. Clean, technical style suitable for research paper.",
        "alt_text": "Vaked architecture: Declaration → Materialization → Enforcement stack",
        "size": "1024x768",
        "output": "docs/images/architecture.png",
    },
    "pola-flow": {
        "prompt": "Diagram illustrating Principle of Least Privilege (POLA) in Vaked: Show a principal (agent) with granted capabilities [fs.repo_ro] attempting to use fs.repo_rw (denied). Show another principal with fs.repo_rw delegating to subordinate with fs.repo_ro (correct attenuation). Use arrows, capability labels, checkmarks (✓) and X marks. Technical, clear.",
        "alt_text": "POLA enforcement: capability attenuation along delegation edges",
        "size": "1024x768",
        "output": "docs/images/pola-flow.png",
    },
    "capability-graph": {
        "prompt": "Visual representation of a capability graph topology: 3-4 principals (shown as circles/nodes) with labeled capabilities inside (fs.repo_rw, network.read, etc.). Directed edges between principals show delegation relationships. Edge labels show attenuation (e.g., repo_rw→repo_ro). Color-code capability domains (file=blue, network=green, process=orange). Technical diagram style.",
        "alt_text": "Capability graph: principals, capabilities, and delegation edges",
        "size": "1024x768",
        "output": "docs/images/capability-graph.png",
    },
    "benchmark-scalability": {
        "prompt": "Line graph showing Vaked compiler scalability: X-axis: number of workers (8, 64, 1024, 10000), Y-axis: compile time (ms, log scale from 50 to 150000). Show three lines: Parse time, Check time, Lower time. Markers at 8/1024/10000 showing measured end-to-end compile time (~0.22s / ~1.6s / ~25s), with the lower stage growing super-linearly. Legend, grid, professional scientific style.",
        "alt_text": "Benchmark scalability: compile time vs. number of workers",
        "size": "1024x600",
        "output": "docs/images/benchmark-scalability.png",
    },
    "type-system-rules": {
        "prompt": "Visual summary of Vaked's type system POLA rules: Three boxes showing: (1) Use Check rule (used(p) ⊑ granted(p)), (2) Attenuation Check rule (granted(receiver) ⊑ granted(sender)), (3) Partial Order rule (a ≤ b forms transitive closure). Each box includes a simple example. Mathematical notation with clear explanations. Clean, publication-quality.",
        "alt_text": "Vaked type system POLA rules: use check, attenuation, partial order",
        "size": "1024x768",
        "output": "docs/images/type-system-rules.png",
    },
    "compilation-pipeline": {
        "prompt": "Vaked compilation pipeline diagram: Input (.vaked file) → Lexer → Parser → Resolver → Elaborator → Type Checker → Lowerer → Output (flake.nix, Zig configs, provenance.json). Show intermediate representations (AST, LPG, Typed Graph). Horizontal flow, color-coded stages, arrows between steps.",
        "alt_text": "vakedc compilation pipeline: parse → check → lower stages",
        "size": "1024x600",
        "output": "docs/images/compilation-pipeline.png",
    },
    "threat-model-summary": {
        "prompt": "Threat model overview diagram: Two columns. LEFT: 'What Vaked Guarantees' (green checkmarks): static POLA verification, decidable checking, deterministic lowering. RIGHT: 'What Vaked Does NOT Guarantee' (red X marks): runtime enforcement, compromise of root authority, timing attacks. Clear separation with icons/symbols.",
        "alt_text": "Vaked threat model: guarantees vs. out-of-scope threats",
        "size": "1024x768",
        "output": "docs/images/threat-model-summary.png",
    },
    "optimization-roadmap": {
        "prompt": "Roadmap visualization: Timeline from v0.2 to v1.0 showing optimization phases: Phase 1 (binary search indexing, 2-5× speedup), Phase 2 (partial order caching, +1-2×), Phase 3 (parallelization, +2-4×), Phase 4 (incremental checking, +5-50×), Rust rewrite (+10-20×). Show cumulative speedup targets and 10K-worker performance goals. Horizontal timeline with colored boxes.",
        "alt_text": "Optimization roadmap: phases from O(n²) to O(n log n) compilation",
        "size": "1024x600",
        "output": "docs/images/optimization-roadmap.png",
    },
    "operator-field-example": {
        "prompt": "Diagram of Operator-Field example: Runtime box containing two fibers (Supervisor and Agent). Supervisor has capabilities [fs.repo_rw, process.signal]. Agent has [fs.repo_ro]. Mesh edge shows Supervisor → Agent delegation. Include schema fields (name, engine, policy, capabilities). Color-code capability levels. Annotation showing POLA check passing.",
        "alt_text": "Operator-field case study: 2-fiber orchestration with POLA verification",
        "size": "1024x768",
        "output": "docs/images/operator-field-example.png",
    },
}


def generate_image(name: str, spec: dict) -> bool:
    """Generate a single image via OpenRouter API."""
    if not OPENROUTER_API_KEY:
        print(f"❌ {name}: OPENROUTER_API_KEY not set")
        return False

    output_path = Path(spec["output"])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"⏳ Generating {name}...")
    print(f"   Prompt: {spec['prompt'][:60]}...")

    try:
        # Try with DALL-E 3 via OpenRouter
        response = requests.post(
            OPENROUTER_API_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "openai/dall-e-3",  # or other models available via OpenRouter
                "prompt": spec["prompt"],
                "n": 1,
                "size": spec["size"],
                "quality": "hd",
            },
            timeout=60,
        )

        if response.status_code != 200:
            print(f"❌ {name}: API error {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False

        data = response.json()
        image_url = data["data"][0]["url"]

        # Download the image
        img_response = requests.get(image_url, timeout=30)
        if img_response.status_code != 200:
            print(f"❌ {name}: Failed to download image")
            return False

        # Save image
        with open(output_path, "wb") as f:
            f.write(img_response.content)

        print(f"✅ {name} → {output_path}")
        return True

    except Exception as e:
        print(f"❌ {name}: {e}")
        return False


def generate_metadata_file() -> None:
    """Generate a metadata file with image alt-text and usage instructions."""
    metadata = {
        "images": {
            name: {
                "alt_text": spec["alt_text"],
                "prompt": spec["prompt"],
                "size": spec["size"],
                "output": spec["output"],
                "markdown_usage": f"![{spec['alt_text']}]({spec['output']})",
            }
            for name, spec in IMAGES.items()
        },
        "generated_at": __import__("datetime").datetime.now().isoformat(),
        "api": "OpenRouter (DALL-E 3)",
    }

    metadata_path = Path("docs/images/metadata.json")
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"\n📋 Metadata → {metadata_path}")


def main():
    """Generate images based on command-line arguments."""
    if not OPENROUTER_API_KEY:
        print("❌ Error: OPENROUTER_API_KEY environment variable not set")
        print("Usage: OPENROUTER_API_KEY='your-key' python3 generate_images.py")
        sys.exit(1)

    args = sys.argv[1:] if len(sys.argv) > 1 else ["--list"]

    if "--list" in args:
        print("Available images:")
        for name, spec in IMAGES.items():
            print(f"  - {name}: {spec['alt_text']}")
        print(f"\nTotal: {len(IMAGES)} images")
        print(f"\nUsage:")
        print(f"  python3 generate_images.py --all           # Generate all")
        print(f"  python3 generate_images.py --image NAME    # Generate one")
        return

    if "--all" in args:
        print(f"Generating {len(IMAGES)} images...\n")
        succeeded = sum(generate_image(name, spec) for name, spec in IMAGES.items())
        print(f"\n✅ Generated {succeeded}/{len(IMAGES)} images")
        generate_metadata_file()
        return

    if "--image" in args:
        idx = args.index("--image")
        if idx + 1 >= len(args):
            print("❌ Usage: --image NAME")
            sys.exit(1)
        name = args[idx + 1]
        if name not in IMAGES:
            print(f"❌ Unknown image: {name}")
            print(f"Available: {', '.join(IMAGES.keys())}")
            sys.exit(1)
        if generate_image(name, IMAGES[name]):
            generate_metadata_file()
        return

    print("❌ Unknown arguments")
    print("Usage: python3 generate_images.py [--list|--all|--image NAME]")


if __name__ == "__main__":
    main()

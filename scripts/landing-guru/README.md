# Landing Guru — Landing Page Generation Suite

Helper scripts for building the Vaked landing site and generating architectural diagrams.

## Scripts

### `diagram-generator.py`

Scans Markdown and EBNF files across the documentation tree for mentions of "architecture", "flow", "pipeline", and "graph". For each match, generates a templated D2 diagram source and optionally renders to SVG.

**Usage:**
```bash
python3 diagram-generator.py [--repo-root <path>] [-v] [--no-render]
```

**Options:**
- `--repo-root <path>`: Repository root (auto-detected if omitted)
- `-v, --verbose`: List all scanned files
- `--no-render`: Write D2 sources only; skip SVG rendering

**Output:**
- D2 sources: `docs/assets/diagrams/*.d2`
- SVG renders (if d2 CLI available): `docs/assets/diagrams/*.svg`
- Metadata: `docs/assets/diagrams/.diagram-report.json`

**Example:**
```bash
# Generate all diagrams and render to SVG (requires d2 CLI)
python3 scripts/landing-guru/diagram-generator.py

# Generate D2 sources only (no rendering)
python3 scripts/landing-guru/diagram-generator.py --no-render

# Verbose mode to see which files are scanned
python3 scripts/landing-guru/diagram-generator.py -v
```

**Templates:**
The script uses type-specific D2 templates based on keyword match:
- `architecture` → three-layer Declaration/Materialization/Enforcement stack
- `flow` → input-process-output flow
- `pipeline` → Parse→Check→Lower→Emit compilation pipeline
- `graph` → generic node-edge graph with capability labels

To customize diagrams, edit the context in the source markdown/EBNF file or modify templates in `_d2_*_template()` methods.

### `landing-builder.py`

Reads JSON cache files from `.landing-cache/` and renders static HTML landing pages:
- `docs/website/index.html` — hero + featured examples (first 6)
- `docs/website/examples.html` — full example catalog
- `docs/website/docs.html` — documentation site map
- `docs/website/og-image.svg` — open-graph preview image

**Usage:**
```bash
python3 landing-builder.py [--repo-root <path>] [-v]
```

**Options:**
- `--repo-root <path>`: Repository root (auto-detected if omitted)
- `-v, --verbose`: Show detailed progress

**Input:**
Reads from `.landing-cache/`:
- `examples-catalog.json` — array of `{name, description, tags, filepath}`
- `coherence-graph.json` — array of `{id, title, description}` under `docs` key

**Output:**
- `docs/website/index.html`
- `docs/website/examples.html`
- `docs/website/docs.html`
- `docs/website/og-image.svg`

**Example:**
```bash
# Build landing pages from cache
python3 scripts/landing-guru/landing-builder.py

# With verbose output
python3 scripts/landing-guru/landing-builder.py -v
```

**Empty cache handling:**
If `.landing-cache/` is missing or contains empty JSON, the builder generates blank/template pages with `0 examples, 0 docs`. This is safe — no errors are raised. Populate `.landing-cache/` files to populate the site.

## Integration

### Diagram Generation Workflow
1. Add mentions of "architecture", "flow", "pipeline", or "graph" to your markdown/EBNF files
2. Run `diagram-generator.py`
3. Commit the generated `.d2` files (optional, for version control)
4. SVG renders are not committed; they're generated on demand

### Landing Page Workflow
1. Populate `.landing-cache/examples-catalog.json` with example metadata
2. Populate `.landing-cache/coherence-graph.json` with documentation structure
3. Run `landing-builder.py`
4. Static HTML pages appear in `docs/website/`

## Error Handling

Both scripts handle errors gracefully:
- **diagram-generator.py:** Missing files, read errors, d2 render failures → logged in `.diagram-report.json` but don't halt execution
- **landing-builder.py:** Missing cache files → defaults to empty catalog; JSON decode errors → logged but pages still generated

Errors are printed to stdout; check `.diagram-report.json` for full logs.

## Dependencies

- Python 3.8+
- `d2` CLI (optional, for SVG rendering in diagram-generator)
  - Install: https://d2lang.com/tour/install
  - If not available, diagram-generator skips rendering and writes D2 sources only

## Performance

- **diagram-generator.py:** Scans 60+ docs in ~1s, generates 296 D2 diagrams in ~0.5s
- **landing-builder.py:** Loads cache and renders 4 pages in <100ms

Both are safe to run in CI/CD on every commit.

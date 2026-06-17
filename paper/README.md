# Vaked Genesis Paper

**Title:** Vaked: Capability-Graph Languages for Deterministic Agentic Systems
**Authors:** Peter Lodri (Vaked Research)
**Genesis Seal:** `7c242080f5f821e5eaf563fe2208d60632c451687baf65f4fe8e4a0d226e3ecf`

## Compilation

The paper uses IEEE Computer Society format (`IEEEtran.cls`).

### Option 1: Overleaf (recommended)

Upload `paper.tex` and `bibliography.bib` to Overleaf with IEEEtran template.

### Option 2: Local LaTeX

```bash
# Install LaTeX (macOS)
brew install --cask mactex

# Compile
pdflatex paper.tex
bibtex paper
pdflatex paper.tex
pdflatex paper.tex

# Or use latexmk
latexmk -pdf paper.tex
```

### Option 3: Docker

```bash
docker run --rm -v $(pwd):/workdir texlive/texlive pdflatex paper.tex
```

## Files

| File | Purpose |
|------|---------|
| `paper.tex` | Full manuscript (IEEEtran format) |
| `bibliography.bib` | BibTeX references (internal RFCs + external sources) |
| `metadata.json` | Google Scholar / SEO metadata |
| `scholar.html` | Semantic Scholar / Google Scholar crawler snippet |
| `README.md` | This file |

## Abstract

The paper presents Vaked as a capability-graph language and deterministic runtime that replaces probabilistic AI "wrapper" frameworks with kernel-verified agentic infrastructure. It covers the Genesis architecture, layered daemon implementation, swarm deployment metrics, governance heuristics, and future grammar v0.5 extensions.

## References

14 citations spanning:
- Internal RFCs and design docs (grammar, HCP protocol, Synapse, Sentinel)
- External foundational work (Xerox PARC gossip, Nix deployment model, eBPF security)
- Performance issues (#259, #262) documenting O(N²) → O(N) migration path

## Genesis Binding

The paper's claims are cryptographically bound to the Vaked Genesis Block via DNS TXT record. Any derivative work or citation can independently verify the architectural integrity root.

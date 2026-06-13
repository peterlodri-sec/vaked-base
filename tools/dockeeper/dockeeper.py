#!/usr/bin/env python3
"""doc-keeper — deterministic doc/spec/RFC drift checks for vaked-base.

The pr-review agent twice asserted a doc/file was "missing" when it existed; the
honest fix for "does this reference resolve?" is a checker, not another model. This
agent gates that drift in CI:

  - RFC cross-refs: every `RFC 00NN` mention resolves to a `protocol/rfcs/00NN-*.md`.
    (Restricted to leading-zero numbers so external RFCs like `RFC 9110` are ignored.)
  - Repo-path refs: backticked path tokens in prose (e.g. `0012-lowering.md`,
    `vakedc/lower.py`) that *look* like repo paths must resolve. Keyed on real
    top-level dirs / design-doc numbering so illustrative paths don't false-positive.
  - Stub-README freshness (warn): a README that says "Currently empty" / "Stub"
    whose target dir now holds real code.

Markdown *link* resolution is already covered by tests/spec/test_doc_links.py — not
duplicated here. Errors fail CI; warnings don't unless --strict.

Usage: python3 tools/dockeeper/dockeeper.py [--root DIR] [--strict]
"""
from __future__ import annotations
import argparse
import glob
import os
import re
import sys

DOC_GLOBS = ["docs/**/*.md", "protocol/**/*.md", "vaked/**/*.md", "vaked-agents/**/*.md", "*.md"]
CODE_EXTS = (".md", ".rs", ".zig", ".nix", ".py", ".ebnf", ".vaked", ".json", ".toml", ".sh", ".yml", ".yaml", ".erl", ".ex")
RFC_REF = re.compile(r"\bRFC[ -]?(0\d{3})\b")
BACKTICK = re.compile(r"`([^`\n]+)`")
DESIGN_DOC = re.compile(r"^\d{4}-[\w.-]+\.md$")
STUB_MARK = re.compile(r"currently empty|^stub\b|no daemon is implemented|no implementation", re.IGNORECASE)


def doc_files(root: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for pat in DOC_GLOBS:
        for p in glob.glob(os.path.join(root, pat), recursive=True):
            rp = os.path.realpath(p)
            if os.path.isfile(p) and rp not in seen:
                seen.add(rp)
                out.append(p)
    return sorted(out)


def _topdirs(root: str) -> set[str]:
    dirs = {d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)) and not d.startswith(".")}
    dirs.add(".github")
    return dirs


def check_rfc_refs(root: str, files: list[str]) -> tuple[list, list]:
    have = set()
    for f in glob.glob(os.path.join(root, "protocol/rfcs/*.md")):
        m = re.match(r"(\d{4})-", os.path.basename(f))
        if m:
            have.add(m.group(1))
    max_have = max((int(n) for n in have), default=0)
    errs, warns = [], []
    for f in files:
        if "/protocol/" not in f.replace(os.sep, "/"):
            continue  # vaked's RFC refs live in protocol docs; avoids external-RFC noise
        with open(f, encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh, 1):
                for m in RFC_REF.finditer(line):
                    num = m.group(1)
                    if num in have:
                        continue
                    msg = f"RFC {num} referenced but protocol/rfcs/{num}-*.md not found"
                    # Within the existing range = a gap/typo (error); beyond it = a
                    # planned/forward reference (warn, don't fail CI).
                    (errs if int(num) <= max_have else warns).append((os.path.relpath(f, root), i, msg))
    return errs, warns


def _looks_like_path(tok: str, topdirs: set[str]) -> bool:
    base = tok.split("#", 1)[0]
    base = re.sub(r":\d+(-\d+)?$", "", base)  # strip a trailing path:line[-col]
    if not base or "://" in base or base.startswith(("#", "/")) or " " in base:
        return False
    # Templates/globs in prose are not literal paths.
    if any(c in base for c in "<>*?{}") or ".." in base:
        return False
    if DESIGN_DOC.match(base):
        return True
    if "/" in base and base.endswith(CODE_EXTS):
        return base.split("/", 1)[0] in topdirs
    return False


def _resolves(tok: str, docfile: str, root: str) -> bool:
    base = re.sub(r":\d+(-\d+)?$", "", tok.split("#", 1)[0])
    if os.path.exists(os.path.join(root, base)) or os.path.exists(os.path.join(os.path.dirname(docfile), base)):
        return True
    if DESIGN_DOC.match(base):  # design docs are referenced by bare name; search the tree
        return bool(glob.glob(os.path.join(root, "**", os.path.basename(base)), recursive=True))
    return False


# Design/plan/decision docs intentionally describe *future* files — exclude them
# from path-ref resolution (they'd false-positive on yet-to-be-created paths).
FORWARD_LOOKING = ("docs/superpowers/", "docs/decisions/")


def check_path_refs(root: str, files: list[str]) -> list[tuple[str, int, str]]:
    topdirs = _topdirs(root)
    errs = []
    for f in files:
        if any(seg in f.replace(os.sep, "/") for seg in FORWARD_LOOKING):
            continue
        with open(f, encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh, 1):
                for m in BACKTICK.finditer(line):
                    tok = m.group(1).strip()
                    if _looks_like_path(tok, topdirs) and not _resolves(tok, f, root):
                        errs.append((os.path.relpath(f, root), i, f"`{tok}` looks like a repo path but does not resolve"))
    return errs


def _has_code(dirpath: str) -> bool:
    code = (".rs", ".zig", ".erl", ".ex", ".py")
    for dirp, _dirs, names in os.walk(dirpath):
        for n in names:
            if n.endswith(code):
                return True
    return False


STUB_TARGETS = {"daemons/README.md": "daemons", "docs/runtime/README.md": "daemons", "protocol/README.md": "protocol"}


def check_stub_freshness(root: str) -> list[tuple[str, int, str]]:
    warns = []
    for readme, target in STUB_TARGETS.items():
        rp = os.path.join(root, readme)
        tp = os.path.join(root, target)
        if not os.path.isfile(rp) or not os.path.isdir(tp):
            continue
        with open(rp, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        if STUB_MARK.search(text) and _has_code(tp):
            warns.append((readme, 0, f"declares stub/empty but {target}/ now contains code — update the README"))
    return warns


def run(root: str, strict: bool = False) -> int:
    root = os.path.abspath(root)
    files = doc_files(root)
    rfc_errs, rfc_warns = check_rfc_refs(root, files)
    errors = rfc_errs + check_path_refs(root, files)
    warnings = rfc_warns + check_stub_freshness(root)

    def emit(kind, items):
        for path, line, msg in items:
            loc = f"{path}:{line}" if line else path
            print(f"::{kind}:: {loc} — {msg}" if os.environ.get("GITHUB_ACTIONS") else f"[{kind}] {loc} — {msg}")

    emit("error", errors)
    emit("warning", warnings)
    print(f"\ndoc-keeper: {len(errors)} error(s), {len(warnings)} warning(s) across {len(files)} docs")
    if errors or (strict and warnings):
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="doc/spec/RFC drift checks for vaked-base")
    ap.add_argument("--root", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    ap.add_argument("--strict", action="store_true", help="treat warnings as failures too")
    args = ap.parse_args()
    return run(args.root, args.strict)


if __name__ == "__main__":
    sys.exit(main())

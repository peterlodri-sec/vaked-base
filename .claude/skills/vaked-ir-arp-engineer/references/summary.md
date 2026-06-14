This file is a merged representation of a subset of the codebase, containing specifically included files and files not matching ignore patterns, combined into a single document by Repomix.

# Summary

## Purpose

This is a reference codebase organized into multiple files for AI consumption.
It is designed to be easily searchable using grep and other text-based tools.

## File Structure

This skill contains the following reference files:

| File | Contents |
|------|----------|
| `project-structure.md` | Directory tree with line counts per file |
| `files.md` | All file contents (search with `## File: <path>`) |
| `tech-stacks.md` | Languages, frameworks, and dependencies per package (search with `## Tech Stack: <path>`) |
| `summary.md` | This file - purpose and format explanation |

## Usage Guidelines

- This file should be treated as read-only. Any changes should be made to the
  original repository files, not this packed version.
- When processing this file, use the file path to distinguish
  between different files in the repository.
- Be aware that this file may contain sensitive information. Handle it with
  the same level of security as you would the original repository.

## Notes

- Some files may have been excluded based on .gitignore rules and Repomix's configuration
- Binary files are not included in this packed representation. Please refer to the Repository Structure section for a complete list of file paths, including binary files
- Only files matching these patterns are included: docs/language/**, vakedc/**, vaked/**
- Files matching these patterns are excluded: **/__pycache__/**, **/*.pyc
- Files matching patterns in .gitignore are excluded
- Files matching default ignore patterns are excluded
- Files are sorted by Git change count (files with more changes are at the bottom)

## Statistics

46 files | 9,065 lines

| Language | Files | Lines |
|----------|------:|------:|
| Markdown | 16 | 3,097 |
| VAKED | 16 | 561 |
| Python | 9 | 4,889 |
| JSON | 2 | 152 |
| JSONL | 1 | 3 |
| NIX | 1 | 103 |
| EBNF | 1 | 260 |

**Largest files:**
- `vakedc/lower.py` (1,400 lines)
- `vakedc/check.py` (1,277 lines)
- `vakedc/parser.py` (844 lines)
- `docs/language/0012-lowering.md` (830 lines)
- `docs/language/0011-type-system.md` (646 lines)
- `vaked/schema/parallel-types.md` (508 lines)
- `vakedc/lexer.py` (388 lines)
- `vakedc/resolve.py` (345 lines)
- `vakedc/__main__.py` (269 lines)
- `vaked/grammar/vaked-v0-plus.ebnf` (260 lines)
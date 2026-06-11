---
description: Run the vakedc pipeline (parse|check|lower|all) on a .vaked file with BuildKit-style output.
---

Run the Vaked compiler pipeline for: **$ARGUMENTS**

1. Parse `$ARGUMENTS` into a subcommand (`parse` | `check` | `lower` | `all`; default `all` if only a file is given) and the target `.vaked` file (+ optional out dir).
2. From the `vaked-base` repo root, run it through the cached devshell + BuildKit-style runner:
   - `task all -- <file>` (or `task <sub> -- <file>`), which wraps `tools/vaked-run.sh`.
   - If `task`/`nix` is unavailable, fall back to `bash tools/vaked-run.sh <sub> <file>`.
3. Report the step results. On `check` diagnostics or a `lower` refusal, surface them verbatim.
4. If the run reveals a **gap in the language itself** (a construct that can't be expressed, a wrong lowering, a type the checker can't represent), follow the `vaked-compiler-dev` convention and **open a GitHub issue on `peterlodri-sec/vaked-base`** rather than silently changing the grammar/schema.

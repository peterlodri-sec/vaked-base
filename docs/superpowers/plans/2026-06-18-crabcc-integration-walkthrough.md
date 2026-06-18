# Walkthrough — CrabCC Integration

This walkthrough documents the local verification and testing completed to validate the `crabcc` index setup.

## What Was Tested

We verified the local compilation/indexing behavior of `crabcc 6.3.0` on the target workspace:

1. **Global Store vs. Workspace Local Store:**
   * Checked if `crabcc index build` writes to a workspace-local directory by default.
   * **Result:** It defaults to a global index under `~/.crabcc/repos/<repo-name>-<hash>/index.db`.
   
2. **Local Index Override:**
   * Tested creating a local `.crabcc` directory in the repository root and running `crabcc index build`.
   * **Result:** When `.crabcc` exists in the repository root, `crabcc` writes the SQLite database (`index.db`) directly into `./.crabcc/index.db`. This confirms that caching `.crabcc` in GitHub Actions will successfully persist and reuse the index.

3. **Performance Metrics:**
   * Indexing a project of this size (785 files, 8201 symbols) took less than 2 seconds.

---

## Proof of Indexing & Symbol Resolution

To prove that the generated index is fully functional, we executed a local lookup for the symbol `connect_crabcc` (defined inside `vaked-agents/ci/pr-review/src/agent.rs`):

```bash
$ crabcc lookup sym connect_crabcc
```

### Output:
```json
[
  {
    "name": "connect_crabcc",
    "kind": "function",
    "signature": "pub(crate) async fn connect_crabcc(cfg: &Config) -> Result<McpToolset>",
    "parent": null,
    "file": "vaked-agents/ci/pr-review/src/agent.rs",
    "line_start": 540,
    "line_end": 558,
    "visibility": "pub(crate)"
  }
]
```

This validates that `crabcc`:
* Can correctly parse the codebase.
* Extract functions, visibility, line spans, and exact signatures.
* Interface perfectly with external tools/agents requesting symbol intelligence.

---

## Integration Reference

The implementation details and YAML templates for the target repository are detailed in [implementation_plan.md](file:///Users/peter.lodri/.gemini/antigravity/brain/7b8af58d-7e5c-4db9-8bf3-20318f88648f/implementation_plan.md).

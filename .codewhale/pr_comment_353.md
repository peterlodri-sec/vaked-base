### Review comments addressed — `13327cb`

All 12 inline review suggestions are fixed in `13327cb` (pushed to this branch). Threads resolved. No builds were run on the dev machine (per `CLAUDE.md`); verified locally with `gofmt`, `bash -n`, `ast.parse`, `json.load`, and `yaml.safe_load` (which rejects duplicate keys).

**P1**

- **nix/vaked-mlir.nix** — placeholder fixed-output hash: derivation now `meta.broken = true` with an actionable note. The real sha256 needs a dev-cx53 3-gate build (can't be computed on the M1 dev machine); the placeholder no longer fails as a misleading fetch hash-mismatch. *(follow-up: compute the real hash on dev-cx53, paste it, remove `broken`)*
- **VakedDialect.cpp / HcpDialect.cpp** — ops not registered: `initialize()` now calls `addOperations<GET_OP_LIST>` before `addTypes`, so `vaked.agent` / `vaked.consume` / `hcp.*` are known when the library loads.
- **.dev bearer token (bootstrap.sh / whale-config.json / README.md)** — the literal proxy key `sk-PrsAdrq...` is removed from all three files; bootstrap reads `VAKED_PROXY_KEY` (falling back to `OPENAI_API_KEY`) and degrades the curl check gracefully when unset.

**P2**

- **main.go: mlir-tblgen success** — checked via `errCode` instead of `r.err == nil` (the `[]byte` err is never nil, so valid dialects always reported FAIL).
- **main.go: seal nonexistent input** — `walkHash` now returns an error; a missing/typo path REFUSEs instead of hashing empty input.
- **main.go: repo root for installed binaries** — `resolveRepoRoot()` honors `VAKED_REPO_ROOT` and walks up for `flake.nix`, so Nix `$out/bin` and deployed `/home/dev/bin` binaries find the source tree.
- **proxy-mesh.yaml** — duplicate `database_url` key removed; the env `DATABASE_URL` override is now authoritative.
- **vakedc `passes` subcommand** — registered in `__main__.py` (Taskfile, the corpus harness, and `vaked-cli mlir validate` all invoke `python3 -m vakedc passes`); `--json` output shape matches `vaked-cli`.
- **flake.nix** — `recursiveUpdate` so `devShells.aarch64-darwin.default` survives adding `vaked-mobile` (the `//` shallow-merge had replaced it on Apple Silicon).
- **passes/__init__.py** — WAL + AOT are skipped for workflows that failed Pass 1 topology diagnostics (no `gen/workflow/*.json` for cyclic / depth-exceeded IRs).
- **CMakeLists.txt** — `--gen-op-decls` and `--gen-typedef-decls` `.inc` are now generated for both dialects, so the headers carry op/type declarations.
- **bootstrap.sh prereq guard** — `${missing:-0} -eq 1 && exit 1` (which tried to exec a command named `0`/`1`) replaced with a proper `[ ]` test.

---

⚠️ **Owner action required:** the removed proxy key `sk-PrsAdrqFU4xYhrm3hGLo1Q` is still in this branch's git history (commits `7cafe7497f` / `4988fccf` / `a74eaf24`). Removing it from the files does **not** revoke past exposure — **rotate that key at the LiteLLM proxy** before merging.

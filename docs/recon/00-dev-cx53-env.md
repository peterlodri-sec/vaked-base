# recon env — dev-cx53 (golden bring-up)

Everything runs as `revdev`. Nix-store paths drift on updates — **derive, don't hardcode**
(the Taskfile `run` task derives them).

## one-time setup
- **oracle code** → revdev: `git archive FETCH_HEAD tools vaked | sudo -u revdev tar -x -C ~revdev/oracle-code`
- **pyghidra venv**: `cd ~/oracle && uv venv pgvenv --python 3.13 && uv pip install --python ~/oracle/pgvenv/bin/python <ghidra>/Ghidra/Features/PyGhidra/pypkg/dist/pyghidra-*.whl`  (pulls jpype1 from PyPI)
- **decompiler model**: HF `Th3S/llm4decompile-6.7b-v2-Q4_K_M-GGUF` → `~/oracle/models/` (4.08 GB, magic `GGUF`)
- **ground truth**: `git clone --depth 1 https://github.com/ggml-org/llama.cpp ~/oracle/llama.cpp-src`  (→ non-null fidelity)

## env (derive dynamically)
| var | value |
|-----|-------|
| `GHIDRA_INSTALL_DIR` | `/nix/store/*ghidra*/lib/ghidra` (the dir containing `Ghidra/`) |
| `JAVA_HOME` | `/nix/store/*openjdk*` with `bin/java` — openjdk-21 |
| `LD_LIBRARY_PATH` | dir of `/nix/store/*gcc*lib*/lib/libstdc++.so.6` — **jpype needs it** |
| `PATH` | `$JAVA_HOME/bin:…` — ghidra `LaunchSupport` calls bare `java` |
| `ORACLE_PYGHIDRA_PYTHON` | `~/oracle/pgvenv/bin/python` |

## serve + run
- **llama-server**: `llama-server -m <gguf> --port 8090 --host 127.0.0.1 -c 4096`  (`:8080` is taken by `atticd`)
- health: `GET :8090/health` → `200` when loaded (~9s)
- run: `task -d tools/oracle run TARGET=<lib> FUNCS=a,b,c`  (derives env) — or `oracle.py run` directly

## gotchas (each cost a debug cycle)
- **ghidra 12 Jython** `.py` postScripts are a dead end → use **PyGhidra** (this recipe).
- jpype `ImportError: libstdc++.so.6` → set `LD_LIBRARY_PATH` (above).
- `pyghidra.start()` exit 127 → `java` not on PATH → add `$JAVA_HOME/bin`.
- `llama-cli` exports nothing → target `libllama.so.0` / `libggml-base.so.0`, not the CLI.
- no ground-truth source → fidelity `null` (graceful: policy finalizes, doesn't burn refine passes).
- pathological DWARF (e.g. `zig cc` w/ `-g`) floods ghidra w/ `DWARFDataTypeImporter` errors → compile `-g0` for test binaries.

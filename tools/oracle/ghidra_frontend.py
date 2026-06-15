"""Static frontend: PyGhidra → decompiler pseudo-C per function.

parse_decomp() is pure (tested). run_ghidra() is the impure runner; it invokes
pyghidra_decompile.py via a CPython 3 venv (pyghidra + jpype1 installed), threads
the GHIDRA_INSTALL_DIR/JAVA_HOME/LD_LIBRARY_PATH env, captures stderr, and fails
loudly if no output is produced.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile


def parse_decomp(blob: str) -> dict[str, str]:
    """Parse the {func: pseudo_c} JSON emitted by DecompileExport.py."""
    try:
        data = json.loads(blob)
    except json.JSONDecodeError as e:
        raise ValueError(f"bad decomp json: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("decomp json must be an object")
    return {str(k): str(v) for k, v in data.items()}


def run_ghidra(*, binary: str, functions: list[str], pyghidra_python: str | None = None,
               ghidra_install_dir: str | None = None, java_home: str | None = None,
               libstdcxx_dir: str | None = None, project_dir: str | None = None,
               timeout: float = 1800.0) -> dict[str, str]:
    """Impure. Decompile via PyGhidra (Python 3). Returns {func: pseudo_c}.

    The PyGhidra env (GHIDRA_INSTALL_DIR / JAVA_HOME / LD_LIBRARY_PATH / java on
    PATH) is taken from the explicit args or inherited from the process env. Raises
    RuntimeError with the captured stderr if the decompile produces no output.
    """
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pyghidra_decompile.py")
    py = pyghidra_python or os.environ.get("ORACLE_PYGHIDRA_PYTHON", "python3")
    tmp = project_dir or tempfile.mkdtemp(prefix="oracle-pyghidra-")
    out_json = os.path.join(tmp, "decomp.json")
    env = dict(os.environ)
    gid = ghidra_install_dir or env.get("GHIDRA_INSTALL_DIR")
    jh = java_home or env.get("JAVA_HOME")
    lsd = libstdcxx_dir or env.get("ORACLE_LIBSTDCXX_DIR")
    if gid:
        env["GHIDRA_INSTALL_DIR"] = gid
    if jh:
        env["JAVA_HOME"] = jh
        env["PATH"] = jh + "/bin:" + env.get("PATH", "")
    if lsd:
        env["LD_LIBRARY_PATH"] = lsd + ((":" + env["LD_LIBRARY_PATH"]) if env.get("LD_LIBRARY_PATH") else "")
    proc = subprocess.run([py, script, binary, out_json, ",".join(functions)],
                          env=env, capture_output=True, text=True, timeout=timeout)
    if not os.path.exists(out_json):
        raise RuntimeError(
            "pyghidra decompile produced no output (exit %d).\nstderr tail:\n%s"
            % (proc.returncode, proc.stderr[-2000:]))
    with open(out_json) as fh:
        return parse_decomp(fh.read())

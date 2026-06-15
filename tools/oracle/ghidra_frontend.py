"""Static frontend: Ghidra analyzeHeadless → decompiler pseudo-C per function.

parse_decomp() is pure (tested). run_ghidra() is the impure runner; it invokes
analyzeHeadless with DecompileExport.py as a postScript, which writes a JSON map
{func_name: pseudo_c} to the output path. analyzeHeadless lives under the nix
ghidra package's support/ dir; pass its path explicitly (open item / Taskfile var).
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


def run_ghidra(*, analyze_headless: str, binary: str, functions: list[str],
               project_dir: str | None = None, timeout: float = 1800.0) -> dict[str, str]:
    """Impure. Returns {func: pseudo_c}. Raises CalledProcessError on ghidra failure."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    tmp = project_dir or tempfile.mkdtemp(prefix="oracle-ghidra-")
    out_json = os.path.join(tmp, "decomp.json")
    cmd = [
        analyze_headless, tmp, "oracleProj",
        "-import", binary, "-overwrite",
        "-scriptPath", script_dir,
        "-postScript", "DecompileExport.py", out_json, ",".join(functions),
    ]
    subprocess.run(cmd, check=True, timeout=timeout,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return parse_decomp(open(out_json).read())

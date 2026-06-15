#!/usr/bin/env python3
"""PyGhidra headless decompiler -> {func: pseudo_c} JSON for named functions.

Usage: pyghidra_decompile.py <binary> <out.json> <comma,funcs>
Requires env: GHIDRA_INSTALL_DIR, JAVA_HOME, LD_LIBRARY_PATH (libstdc++), java on PATH.
Run via the pyghidra venv python (pyghidra + jpype1 installed). Validated on
ghidra 12.0.4 / openjdk-21 / pyghidra 3.0.2.
"""
import json
import sys
import tempfile

import pyghidra


def main():
    binary, out_path, funcs_csv = sys.argv[1], sys.argv[2], sys.argv[3]
    wanted = set(f for f in funcs_csv.split(",") if f)
    pyghidra.start(verbose=False)
    from ghidra.app.decompiler import DecompInterface
    from ghidra.util.task import ConsoleTaskMonitor
    result = {}
    with tempfile.TemporaryDirectory() as proj:
        with pyghidra.open_program(binary, project_location=proj, analyze=True) as flat:
            prog = flat.getCurrentProgram()
            ifc = DecompInterface()
            ifc.openProgram(prog)
            mon = ConsoleTaskMonitor()
            for fn in prog.getFunctionManager().getFunctions(True):
                nm = fn.getName()
                if wanted and nm not in wanted:
                    continue
                r = ifc.decompileFunction(fn, 60, mon)
                if r and r.decompileCompleted():
                    result[nm] = r.getDecompiledFunction().getC()
    with open(out_path, "w") as fh:
        json.dump(result, fh)
    sys.stderr.write("pyghidra_decompile: %d funcs -> %s\n" % (len(result), out_path))


if __name__ == "__main__":
    main()

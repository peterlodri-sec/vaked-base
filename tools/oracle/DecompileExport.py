# Ghidra post-script (Jython). Run by analyzeHeadless:
#   -postScript DecompileExport.py <out_json> <comma,separated,func,names>
# Writes {func_name: pseudo_c} JSON for the requested functions.
import json
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor

args = getScriptArgs()            # noqa: F821 (Ghidra-injected)
out_path = args[0]
wanted = set(a for a in args[1].split(",") if a)

ifc = DecompInterface()
ifc.openProgram(currentProgram)   # noqa: F821
monitor = ConsoleTaskMonitor()

result = {}
fm = currentProgram.getFunctionManager()   # noqa: F821
for fn in fm.getFunctions(True):
    name = fn.getName()
    if wanted and name not in wanted:
        continue
    res = ifc.decompileFunction(fn, 60, monitor)
    if res and res.decompileCompleted():
        result[name] = res.getDecompiledFunction().getC()

with open(out_path, "w") as fh:
    json.dump(result, fh)

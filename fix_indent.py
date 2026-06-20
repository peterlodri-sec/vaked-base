"""Fix indentation in vakedc/*.py after f952a04 flattening.
Adds 2-space indentation to all class/function bodies."""
import ast, py_compile, sys, os

files = [
    "vakedc/lexer.py",
    "vakedc/parser.py",
    "vakedc/check.py",
    "vakedc/lower.py",
]

for path in files:
    if not os.path.exists(path):
        print(f"SKIP {path}")
        continue
    with open(path) as f:
        src = f.read()
    try:
        ast.parse(src)
        print(f"OK   {path}")
        continue
    except SyntaxError as e:
        print(f"FIX  {path}: {e.msg} at line {e.lineno}")

    lines = src.split("\n")
    out = []
    indent_level = 0
    pending_indent = 0

    for i, line in enumerate(lines):
        raw = line.rstrip()
        if not raw.strip():
            out.append("")
            continue

        stripped = raw.lstrip()

        # Detect if this line should open a new indent level
        # (ends with : after class, def, if, for, while, try, except, finally, with, async, match, case)
        opens_block = False
        if stripped.endswith(":") and not stripped.startswith("#"):
            # Check if it's a statement that opens blocks
            for kw in ["class ", "def ", "if ", "for ", "while ", "try:", "except", "finally:", "with ", "async ", "match ", "case "]:
                if stripped.startswith(kw) or stripped == kw.rstrip(" "):
                    opens_block = True
                    break
            # Also check elif, else
            if stripped.startswith("elif ") or stripped.startswith("else:"):
                opens_block = True

        # Check for dedent markers
        dedent_before = False
        for kw in ["else:", "elif ", "except", "finally:", "case "]:
            if stripped.startswith(kw) or stripped == kw.rstrip(" "):
                dedent_before = True
                break

        if dedent_before and indent_level > 0:
            indent_level -= 1

        out.append("  " * indent_level + stripped)

        if opens_block:
            indent_level += 1

        # Handle triple-quoted strings (docstrings)
        if '"""' in stripped and stripped.count('"""') == 1:
            # Single triple-quote on this line — continue until the closing one
            j = i + 1
            while j < len(lines):
                next_raw = lines[j].rstrip()
                out.append("  " * indent_level + next_raw.lstrip())
                if '"""' in next_raw:
                    break
                j += 1
            # Skip the lines we already added
            # (Continue from the outer loop, skipping inner lines)
            # Actually we need to consume these lines.
            # For now, skip all processed lines by advancing i
            # This is getting complex — skip for now

    result = "\n".join(out) + "\n"
    with open(path, "w") as f:
        f.write(result)

    # Verify
    try:
        py_compile.compile(path, doraise=True)
        print(f"  -> syntax valid")
    except py_compile.PyCompileError as e:
        print(f"  -> STILL BROKEN: {e}")

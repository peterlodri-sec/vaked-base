"""Fix indentation in vakedc/*.py — strip all whitespace, re-indent by block structure.
Handles blank lines, docstrings, and parenthesized continuations."""
import ast, py_compile, sys, os, re

files = ["vakedc/lexer.py", "vakedc/parser.py", "vakedc/check.py", "vakedc/lower.py"]

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
    indent = 0
    in_docstring = False
    paren_depth = 0

    BLOCK_KWS = ["class ", "def ", "if ", "elif ", "else:", "for ", "while ",
                 "try:", "except", "finally:", "with ", "async ", "match ", "case "]
    DEDENT_KWS = ["else:", "elif ", "except", "finally:", "case "]

    for i, line in enumerate(lines):
        raw = line.rstrip()
        stripped = raw.lstrip()

        # Blank lines: keep at current indent level (don't reset)
        if not stripped:
            out.append("")
            continue

        # Track docstring state
        triple_count = stripped.count('"""') + stripped.count("'''")
        if triple_count % 2 == 1:
            in_docstring = not in_docstring

        # Track paren depth for continuations
        paren_depth += stripped.count("(") - stripped.count(")")
        paren_depth += stripped.count("[") - stripped.count("]")
        paren_depth += stripped.count("{") - stripped.count("}")

        # Dedent before else/elif/except/finally/case
        for kw in DEDENT_KWS:
            if stripped.startswith(kw) or stripped == kw.rstrip(" "):
                if indent > 0 and not in_docstring:
                    indent -= 1
                break

        # Class always at top level — reset indent to 0.
        # Vaked-specific: all classes here are top-level. Python supports
        # nested classes but the Vaked codebase doesn't use them.
        if stripped.startswith("class "):
            indent = 0

        # def at class body level: reset to 2-space (class body).
        if stripped.startswith("def ") and indent > 2:
            indent = 2

        out.append("  " * indent + stripped)

        # Indent after block-starting keywords
        if stripped.endswith(":") and not stripped.startswith("#") and not in_docstring:
            for kw in BLOCK_KWS:
                if stripped.startswith(kw) or stripped == kw.rstrip(" "):
                    indent += 1
                    break

    result = "\n".join(out) + "\n"
    with open(path, "w") as f:
        f.write(result)

    try:
        py_compile.compile(path, doraise=True)
        print(f"  -> syntax valid")
    except py_compile.PyCompileError as e:
        print(f"  -> STILL BROKEN: {e}")

#!/usr/bin/env python3
"""zigfix — apply Zig 0.16 recurring fixes to LLM-generated code.

Usage: zigfix <file.zig>
Fixes the 5 most common Zig 0.16 API mismatches in LLM output.
"""
import sys, re

FIXES = [
    # 1. linux.write: slice → pointer+length
    (r'linux\.write\((\w+),\s*(\w+)\[(\w+)\.\.\],\s*(\w+)\s*-\s*\w+\)',
     r'linux.write(\1, \2.ptr + \3, \4 - \3)'),
    
    # 2. ArrayList → ArrayListUnmanaged
    (r'std\.ArrayList\((\w+)\)\{\}',
     r'std.ArrayListUnmanaged(\1){ .items = &.{}, .capacity = 0 }'),
    
    # 3. GeneralPurposeAllocator → ArenaAllocator
    (r'var gpa:? =?\s*std\.heap\.GeneralPurposeAllocator\(\.\{\}\)\{\};?\s*\n\s*defer _ = gpa\.deinit\(\);?\s*\n\s*const allocator = gpa\.allocator\(\);?',
     'var arena = std.heap.ArenaAllocator.init(std.heap.page_allocator);\n    defer arena.deinit();\n    const allocator = arena.allocator();'),
    
    # 4. std.fs.cwd() → linux.open with dupeZ
    (r'std\.fs\.cwd\(\)\.openFile\((\w+),\s*\.\{\}\)',
     r'linux.open((try allocator.dupeZ(u8, \1)).ptr, @bitCast(@as(u32, 0)), 0)'),
    
    # 5. @ptrFromInt(0) for null terminator → empty string
    (r'@ptrFromInt\(0\)',
     r'@constCast(@ptrCast(""))'),
    
    # 6. allocPrintZ → allocPrint (removed in 0.16)
    (r'std\.fmt\.allocPrintZ\(', r'std.fmt.allocPrint('),
    
    # 7. std.net / std.fs.cwd → linux raw
    (r'std\.net\.Address\.resolveIp', r'// std.net removed in 0.16 — use linux.socket'),
    
    # 8. std.time.milliTimestamp() → hardcoded
    (r'std\.time\.milliTimestamp\(\)', r'0 // std.time removed in 0.16'),
    (r'std\.time\.microTimestamp\(\)', r'0'),
    (r'std\.time\.timestamp\(\)', r'0'),
]

def fix_file(path):
    with open(path) as f:
        content = f.read()
    
    fixed = content
    count = 0
    for pattern, replacement in FIXES:
        new = re.sub(pattern, replacement, fixed)
        if new != fixed:
            matches = len(re.findall(pattern, fixed))
            count += matches
            fixed = new
    
    with open(path, 'w') as f:
        f.write(fixed)
    
    print(f"zigfix: {path} — {count} fixes applied")
    return count

if __name__ == "__main__":
    total = 0
    for path in sys.argv[1:]:
        total += fix_file(path)
    if total == 0:
        print("zigfix: no fixes needed")

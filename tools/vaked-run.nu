#!/usr/bin/env nu
# vaked-run.nu — Nushell runner for the vakedc pipeline (parse → check → lower).
# Replaces the Amber runner. Target: nushell 0.113.1 (PIN this exact version in the
# flake — Nushell is pre-1.0 and ships breaking changes every minor; see the adoption
# research). BuildKit-style colored steps; --no-color / NO_COLOR aware; CI exit codes.
#
#   nu tools/vaked-run.nu all   path/to/file.vaked [out]
#   nu tools/vaked-run.nu check path/to/file.vaked
#   nu tools/vaked-run.nu files *.vaked            # parallel check, ordered output
#
# Idioms verified against 0.113.1: `do { ^cmd } | complete` -> {stdout,stderr,exit_code};
# `par-each --keep-order` for deterministic ordered fan-out.

def paint [on: bool, code: string, s: string]: nothing -> string {
  if $on { $"(ansi $code)($s)(ansi reset)" } else { $s }
}

def color-on [no_color: bool]: nothing -> bool {
  not ($no_color or ("NO_COLOR" in $env))
}

# run one stage; prints a BuildKit-style line; returns the exit code (0 = ok)
def run-step [on: bool, idx: int, total: int, sub: string, file: string, out: string]: nothing -> int {
  let head = $"(paint $on 'light_cyan_bold' '=>') (paint $on 'attr_bold' $'[($idx)/($total)]') (paint $on 'dark_gray' $'vakedc ($sub) ($file)')"
  print $head
  let t0 = (date now)
  let res = (if $sub == "lower" {
    do { ^python3 -m vakedc lower $file --out $out } | complete
  } else {
    do { ^python3 -m vakedc $sub $file } | complete
  })
  let dur = ((date now) - $t0)
  let diag = ($res.stdout + $res.stderr | lines | where { |l| ($l | str trim | is-not-empty) and ($l !~ 'Unicode data version') })
  $diag | each { |l| print $"    ($l)" } | ignore
  if $res.exit_code == 0 {
    print $"(paint $on 'green_bold' '   ✓') ($sub) (paint $on 'dark_gray' (($dur) | into string))"
  } else {
    print $"(paint $on 'red_bold' '   ✗') ($sub) FAILED (paint $on 'dark_gray' (($dur) | into string))"
  }
  $res.exit_code
}

# main: <cmd> <file> [out] [--no-color]   (cmd = parse|check|lower|all)
def main [cmd: string, file: string, out: string = "gen", --no-color]: nothing -> nothing {
  let on = (color-on $no_color)
  print $"(paint $on 'attr_bold' '[+] vaked') (paint $on 'dark_gray' $'pipeline → ($file)')"
  if $cmd == "all" {
    if (run-step $on 1 3 "parse" $file $out) != 0 { exit 1 }
    if (run-step $on 2 3 "check" $file $out) != 0 { exit 1 }
    if (run-step $on 3 3 "lower" $file $out) != 0 { exit 1 }
  } else {
    if (run-step $on 1 1 $cmd $file $out) != 0 { exit 1 }
  }
  print (paint $on "green_bold" "[+] DONE")
}

# parallel check of many files with deterministic ORDERED output (par-each -k).
#   nu tools/vaked-run.nu files a.vaked b.vaked ...
def "main files" [...files: string, --no-color]: nothing -> nothing {
  let on = (color-on $no_color)
  let results = ($files | par-each --keep-order { |f|
    let res = (do { ^python3 -m vakedc check $f } | complete)
    { file: $f, ok: ($res.exit_code == 0) }
  })
  $results | each { |r|
    let mark = if $r.ok { paint $on "green_bold" "✓" } else { paint $on "red_bold" "✗" }
    print $"($mark) ($r.file)"
  } | ignore
  let bad = ($results | where not ok | length)
  print $"(paint $on 'attr_bold' '[+]') ($results | length) checked, ($bad) failed"
  if $bad > 0 { exit 1 }
}

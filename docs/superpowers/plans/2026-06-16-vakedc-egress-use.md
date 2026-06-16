# vakedc E-EGRESS-USE + W-EGRESS-UNREFINED — Implementation Plan

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development.

**Goal:** language-level network-egress POLA in `vakedc/check.py`: a `networkMembrane` may not authorize egress beyond its principal's held `network` grant (E-EGRESS-USE, error); a node with unrefined `network.egress`/`lan` is flagged (W-EGRESS-UNREFINED, warning).

**Spec:** `docs/superpowers/specs/2026-06-16-vakedc-egress-use-design.md`

**Verified facts:** `_node_bindings(decl)` (check.py:1054) reads a decl's `{field: value-prop}`. `_emit(diags, code, file, span, decl, msg, severity="error")` (899). `_leq(cap, a, b)` (1099) — true iff `a ≤ b`; `cap = registry.caps["network"]` (lattice `none<loopback<lan<egress`). `node_grants = {name:[(dom,grant)]}` built in `_check_mesh`; `_check_capability_reachability(mesh_decl, node_decls, node_grants, node_needs, registry, smap, file, diags)` called ~line 1724. `network <name>{}` membranes are `P.Decl` with `kind=="network"`, **siblings of the mesh** in the runtime body. A membrane's `allow` entry = `{"ref":"egress","args":[{"lit":"STRING","value":host}, {"lit":..,"value":port}]}`. Fixtures need NO inline `capability network` (builtins provide it). vakedc is pure-Python → `python3 -m vakedc check` is M3-safe.

**Tests:** `tests/spec/test_vakedc_check.py` (run `python3 -m pytest tests/spec/test_vakedc_check.py -v`, or the repo's test entry). Mirror the E-CAP-USE group (group 5e).

**Constraints:** pure stdlib (+`ipaddress`); MUST NOT add any new *error* to the existing example corpus (only the advisory warning); in-lane (vakedc ours). `git add` only named files.

---

### Task 1: `_check_egress_use` + wiring + fixtures + tests

**Files:** Modify `vakedc/check.py`; create 4 `vaked/examples/types/egress-*.vaked`; modify `tests/spec/test_vakedc_check.py`.

- [ ] **Step 1: fixtures** (create under `vaked/examples/types/`):

`egress-use-exceeds.vaked` (→ `E-EGRESS-USE`):
```
# E-EGRESS-USE: membrane allows public egress for a loopback-only principal.
runtime "egress-exceeds" {
  systems = ["x86_64-linux"]
  mesh m {
    node operator { role = "control" capabilities = [network.loopback] }
    node worker   { role = "w" capabilities = [network.loopback] }
    operator -> worker
  }
  network workerCordon { principal = "worker" default = "deny" allow = [ egress("203.0.113.10", 443) ] }
}
```
`egress-use-ok.vaked` (→ clean, no codes):
```
# OK: principal holds network.egress; the membrane's public allow is within grant.
runtime "egress-ok" {
  systems = ["x86_64-linux"]
  mesh m {
    node operator { role = "control" capabilities = [network.egress] }
    node worker   { role = "w" capabilities = [network.egress] }
    operator -> worker
  }
  network workerCordon { principal = "worker" default = "deny" allow = [ egress("203.0.113.10", 443) ] }
}
```
`egress-unrefined.vaked` (→ `W-EGRESS-UNREFINED` only):
```
# W-EGRESS-UNREFINED: node holds network.egress with no refining membrane.
runtime "egress-unrefined" {
  systems = ["x86_64-linux"]
  mesh m {
    node operator { role = "control" capabilities = [network.egress] }
    node worker   { role = "w" capabilities = [network.egress] }
    operator -> worker
  }
}
```
`egress-use-bad-principal.vaked` (→ `E-EGRESS-USE`):
```
# E-EGRESS-USE: membrane principal names no node in the mesh.
runtime "egress-bad-principal" {
  systems = ["x86_64-linux"]
  mesh m {
    node operator { role = "control" capabilities = [network.loopback] }
    node worker   { role = "w" capabilities = [network.loopback] }
    operator -> worker
  }
  network ghostCordon { principal = "ghost" default = "deny" allow = [ egress("203.0.113.10", 443) ] }
}
```
Verify each with `python3 -m vakedc check <f>` — BEFORE the impl, `egress-use-exceeds`/`bad-principal` check clean (gap), `egress-ok` clean, `egress-unrefined` clean. If any fixture fails to resolve `network.*` (E-CAP-UNKNOWN-DOMAIN), add an inline `capability network { grant none loopback lan egress  order none < loopback < lan < egress }` like `cap-use-partial.vaked` — but the probe confirmed builtins suffice, so this should not be needed.

- [ ] **Step 2: failing tests** — add a group to `tests/spec/test_vakedc_check.py` mirroring the `_CAP_USE` block (uses `vakedc.check_source(open(path).read(), rel, builtins_cache=_builtins_cache())`):

```python
_EGRESS_USE = "E-EGRESS-USE"
_EGRESS_UNREF = "W-EGRESS-UNREFINED"
_EGRESS_DIR = os.path.join(REPO, "vaked", "examples", "types")
_EGRESS_CASES = [
    ("egress-use-exceeds.vaked",       [_EGRESS_USE]),
    ("egress-use-ok.vaked",            []),
    ("egress-unrefined.vaked",         [_EGRESS_UNREF]),
    ("egress-use-bad-principal.vaked", [_EGRESS_USE]),
]

def _test_egress_use(lines):
    ok = True
    cache = _builtins_cache()
    for base, expect in _EGRESS_CASES:
        path = os.path.join(_EGRESS_DIR, base)
        rel = os.path.relpath(path, REPO)
        diags = vakedc.check_source(open(path, encoding="utf-8").read(), rel, builtins_cache=cache)
        codes = sorted(d.code for d in diags)
        if codes != sorted(expect):
            ok = False
            lines.append(f"  FAIL egress-use: {base} expected {sorted(expect)}, got {codes}")
            continue
        for d in diags:
            if d.code == _EGRESS_USE and d.severity != "error":
                ok = False; lines.append(f"  FAIL egress-use: {base} {_EGRESS_USE} not error")
            if d.code == _EGRESS_UNREF and d.severity != "warning":
                ok = False; lines.append(f"  FAIL egress-use: {base} {_EGRESS_UNREF} not warning")
            if d.code in (_EGRESS_USE, _EGRESS_UNREF) and (d.byteStart, d.byteEnd) == (0, 0):
                ok = False; lines.append(f"  FAIL egress-use: {base} {d.code} not source-mapped")
    # corpus guard: the oracle team graph must NOT raise E-EGRESS-USE (its cordons match grants)
    ot = os.path.join(REPO, "vaked", "examples", "oracle-team.vaked")
    d2 = vakedc.check_source(open(ot, encoding="utf-8").read(),
                             os.path.relpath(ot, REPO), builtins_cache=cache)
    if any(d.code == _EGRESS_USE for d in d2):
        ok = False; lines.append("  FAIL egress-use: oracle-team.vaked raised E-EGRESS-USE")
    return ok
```
Wire `_test_egress_use` into the file's runner exactly as `_test_cap_use` is invoked (find where `_test_cap_use(lines)` is called in the main test driver and add `ok &= _test_egress_use(lines)` alongside). Run the suite → the egress cases FAIL (codes empty, expected non-empty) before the impl.

- [ ] **Step 3: implement** in `vakedc/check.py`. Add `import ipaddress` near the stdlib imports. Add these helpers + the check function (place `_check_egress_use` near `_check_cap_use`):

```python
_LOOPBACK_HOST_NAMES = frozenset(("localhost",))


def _lit_str(v):
    if isinstance(v, dict) and (v.get("lit") or "").upper() == "STRING":
        return v.get("value")
    return None


def _required_egress_grant(host):
    """The network-lattice level an allow-host implies: loopback < lan < egress."""
    h = (host or "").strip()
    if h in _LOOPBACK_HOST_NAMES:
        return "loopback"
    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        return "egress"          # a non-loopback DNS name -> public egress (conservative)
    if ip.is_loopback:
        return "loopback"
    if ip.is_private:
        return "lan"
    return "egress"


def _egress_allow_hosts(allow_vprop):
    """Hosts from a membrane `allow` value-prop (list of egress(host, port) app-calls)."""
    hosts = []
    if isinstance(allow_vprop, list):
        for e in allow_vprop:
            if isinstance(e, dict) and e.get("ref") == "egress":
                args = e.get("args") or []
                if args:
                    h = _lit_str(args[0])
                    if h is not None:
                        hosts.append(h)
    return hosts


def _grant_max(cap, grants):
    """The strongest grant under cap's order (network is a chain)."""
    best = None
    for g in grants:
        if best is None or _leq(cap, best, g):
            best = g
    return best


def _check_egress_use(mesh_decl, node_decls, node_grants, network_decls,
                      registry, smap, file, diags):
    """Network-domain POLA (the dual of E-CAP-USE / W-POLA-EXCESS):

    * **E-EGRESS-USE** (error) — a `networkMembrane` `allow` set implies an egress
      level its principal's held `network` grant does not dominate (a membrane that
      authorizes egress the capability graph never granted), or whose `principal`
      names no node in the mesh.
    * **W-EGRESS-UNREFINED** (warning) — a node holds `network.egress`/`lan` with no
      `networkMembrane` refining it (unbounded egress; least-authority advisory)."""
    cap = registry.caps.get("network")
    if cap is None:
        return
    net_grants = {n: [g for (d, g) in (node_grants.get(n) or []) if d == "network"]
                  for n in node_decls}
    refined = set()
    for mname in sorted(network_decls):
        mdecl = network_decls[mname]
        bindings, _order = _node_bindings(mdecl)
        principal = _lit_str(bindings.get("principal"))
        span = (mdecl.byteStart, mdecl.byteEnd, mdecl.line, mdecl.col)
        if principal is not None:
            refined.add(principal)
        hosts = _egress_allow_hosts(bindings.get("allow"))
        if not hosts:
            continue
        required = _grant_max(cap, [_required_egress_grant(h) for h in hosts])
        if principal not in node_decls:
            _emit(diags, "E-EGRESS-USE", file, span, mesh_decl,
                  f"membrane `{mname}` names principal `{principal}` which is not a node "
                  f"in mesh `{mesh_decl.name}` — a membrane cannot refine a network grant "
                  f"no node holds (0026)")
            continue
        held = net_grants.get(principal) or []
        if not any(_leq(cap, required, h) for h in held):
            held_str = ", ".join("network.%s" % h for h in held) or "no network grant"
            _emit(diags, "E-EGRESS-USE", file, span, mesh_decl,
                  f"membrane `{mname}` allows egress at level `{required}` for principal "
                  f"`{principal}` which holds {held_str} — a membrane cannot authorize "
                  f"egress beyond the principal's granted network capability (0026)")
    for name in sorted(node_decls):
        unrefined = sorted(g for g in (net_grants.get(name) or []) if g in ("egress", "lan"))
        if unrefined and name not in refined:
            st = node_decls[name]
            nspan = (st.byteStart, st.byteEnd, st.line, st.col)
            cspan = (smap.field_value_span(st.byteStart, st.byteEnd, "capabilities")
                     if smap else None) or nspan
            _emit(diags, "W-EGRESS-UNREFINED", file, cspan, mesh_decl,
                  f"node `{name}` holds `network.{unrefined[-1]}` but no networkMembrane "
                  f"refines it — egress is unbounded (least-authority advisory; add a "
                  f"`network` membrane with an `allow` set)", severity="warning")
```

Wire it: (a) thread `network_decls` into `_check_mesh` (add a keyword param defaulting to `None`); (b) in the caller (`_check_decl_tree`, where `_check_mesh` is invoked for `kind=="mesh"`), build `child_networks = {st.name: st for st in <runtime/parent body> if isinstance(st, P.Decl) and st.kind == "network"}` and pass it; (c) inside `_check_mesh`, after the `_check_capability_reachability(...)` call, add `_check_egress_use(mesh_decl, node_decls, node_grants, network_decls or {}, registry, smap, file, diags)`. **Read the actual `_check_mesh`/`_check_decl_tree` signatures and adapt precisely** — the membranes are siblings of the mesh in the same parent body, so the parent (`_check_decl_tree`) is where they're in scope to collect and pass down.

- [ ] **Step 4: run** — `python3 -m vakedc check` on each fixture gives exactly its expected codes; the test suite group passes; **the full example corpus + `python3 -m pytest tests/spec/test_vakedc_check.py` shows NO new E-EGRESS-USE errors** (only W-EGRESS-UNREFINED warnings on the 9 unrefined-egress examples — confirm those are warnings, not errors, and don't fail any existing exact-code assertion; if an existing test asserts an exact code set on one of those 9 files, update it to include `W-EGRESS-UNREFINED`).

- [ ] **Step 5: commit**
```bash
git add vakedc/check.py vaked/examples/types/egress-use-exceeds.vaked vaked/examples/types/egress-use-ok.vaked vaked/examples/types/egress-unrefined.vaked vaked/examples/types/egress-use-bad-principal.vaked tests/spec/test_vakedc_check.py
git commit -m "feat(vakedc): E-EGRESS-USE + W-EGRESS-UNREFINED — network-membrane POLA (dual of E-CAP-USE)"
```

---

### Task 2: docs

**Files:** Modify a `docs/language/` reference (the POLA / 0026 area) + `.DEV.TODO`.

- [ ] Add a short subsection documenting E-EGRESS-USE (error: membrane allow-set ≤ principal's network grant) + W-EGRESS-UNREFINED (warning: unrefined egress), as the network-domain dual of E-CAP-USE/W-POLA-EXCESS; note it promotes thread-1's tool-local `tools/oracle/roster_from_vaked.check_roster_egress` to a language pass. Find the existing E-CAP-USE / POLA doc (grep `docs/ -rl "E-CAP-USE"`) and add alongside.
- [ ] `.DEV.TODO`: mark "vakedc E-EGRESS-USE pass — DONE"; note follow-ups (RFC formalization; port to vakedz).
- [ ] Commit: `docs(vakedc): document E-EGRESS-USE + W-EGRESS-UNREFINED (network-domain POLA)`.

## Final verification
- [ ] `python3 -m pytest tests/spec/test_vakedc_check.py -v` green (or the repo test runner).
- [ ] No new E-EGRESS-USE error anywhere in `vaked/examples/` (the corpus guard).
- [ ] Final whole-branch review (focus: corpus-safety; lattice classification correctness; determinism).

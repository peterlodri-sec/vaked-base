# vaked-oracle — kernel integration

**How oracle plugs into the vaked-aegis evidence seam and how the NixOS watcher
module is deployed from vaked-base to nix-base.**

---

## 1. The evidence seam (`bridge.py`)

**vaked-aegis** (`tools/dogfood/`) consumes transition evidence as a
`observed_effects` dict — `{"writes": [...], "deletes": [...]}` — where the
values are sorted lists of file paths affected by a proposer transition. Every
accepted transition in the kernel's WAL carries this shape.

**vaked-oracle** produces a different kind of artifact: a finding record that
captures decompilation output and runtime traces, not a code transition. The
bridge makes the two shapes speak to each other.

### `to_observed_effects`

```python
bridge.to_observed_effects(
    finding: dict,
    *,
    files_written: list[str] | None = None,
    files_deleted: list[str] | None = None,
) -> dict
```

Returns `{"writes": sorted(files_written or []), "deletes": sorted(files_deleted
or [])}`. The `finding` argument is accepted for API symmetry but is not
inspected here — the caller determines which files the oracle run produced
(the finding JSON itself, any report files, the JSONL ledger). This keeps
bridge.py pure and separately testable.

**Typical call in a wired-up run:**

```python
finding_path = oracle.persist_finding(finding, findings_dir="~/oracle/findings")
oe = bridge.to_observed_effects(finding, files_written=[finding_path])
# oe == {"writes": ["~/oracle/findings/<sha256>.json"], "deletes": []}
```

The kernel's capability gate (`tools/dogfood/capability.py`) checks that
`oe["writes"]` is a subset of the proposer's declared scope. Because oracle
runs as `revdev` with a narrow write-scope over its own `~/oracle/` workspace,
this check passes as long as findings are written there.

### `attach_transition`

```python
bridge.attach_transition(finding: dict, transition_hash: str) -> dict
```

Returns a deep copy of `finding` with `transition_xref` set to
`transition_hash`. This field links the finding to a specific kernel WAL
entry — the entry recording a transition in which the oracle's RE output was
used as evidence. It is a cross-reference across two hash-chained ledgers (the
oracle's own `events.jsonl` and the kernel's `eventd` WAL).

Slice 2 populates it (`tools/oracle/dogfood_bridge.py`): `ground_finding` records
the finding as a kernel transition and feeds the accepted WAL entry's hash back
here, creating a bidirectional link between the RE evidence and the transition
that recorded it.

---

## 2. The double-dogfood link (wired in slice 2)

The `transition_xref` field is the seam for the "double-dogfood" framing: oracle
reverse-engineers the LLM runtime; the RE findings ground a vaked-aegis proposer
transition; that transition's WAL hash links back to the finding.

```
oracle finding <────── transition_xref ──────> aegis WAL entry
    │                                               │
    └── ledger.verify()                             └── kernel.verify()
        (oracle events.jsonl)                           (eventd WAL)
```

Both sides are tamper-evident independently (each has its own hash chain); the
link is the content hash of the WAL entry, so it survives replay.

**Slice 2 wires this up** (`tools/oracle/dogfood_bridge.py`). `ground_finding`
records the finding as a real aegis kernel transition by reusing
`tools/dogfood/kernel.judge()` — the proposer materializes the finding artifact
into a capability-scoped workspace; the kernel gates it (capability, declared-vs-
actual, replay-stable) and appends it to the eventd WAL. The accepted WAL entry's
hash is attached to the finding (`bridge.attach_transition`) and the linked
finding is appended to the oracle's ralphcore ledger.

The hash cycle is broken by construction: the **WAL** records the finding
*without* `transition_xref` (the post-image it hashes), while the **oracle ledger**
records it *with* the xref. `verify_xref` proves both directions —
`finding.transition_xref` resolves to a WAL entry whose `actual_effects.writes`
contains the finding's path — and that both chains verify independently.

CLI:

    oracle ground --finding <f.json> --root <ws> --scope findings \
                  --wal-path <wal> --blobs <blobs> --ledger <events.jsonl>
    oracle verify-xref --finding <linked.json> --wal-path <wal> --ledger <events.jsonl>

NOTE: `--wal-path`/`--blobs` must resolve outside `--root` (the kernel snapshots
the whole non-git root subtree); the CLI defaults them to a `.aegis-wal/` sibling.

---

## 3. nix-base ↔ vaked-base watcher deploy path

The eBPF watcher is authored in vaked-base but runs as a system service on
dev-cx53, whose host config lives in the private **nix-base** repo. The two
repos are structurally separate (different codebases, different deploy cadences).
The deploy path is manual for slice 1.

### Module authored here (vaked-base)

`tools/oracle/oracle-ebpf-watcher.nix` — defines the systemd service, bpftrace
in the service PATH, the RuntimeDirectory, the socket permissions, and the
`oracle-watcher` group. `tools/oracle/watcher_daemon.py` is the Python daemon
it runs.

The NixOS module header documents the full deploy procedure:

```nix
# DEPLOY (manual, on the box; nix-base and vaked-base are SEPARATE repos):
#   1. Copy this module + tools/oracle/watcher_daemon.py into the nix-base
#      dev-cx53 host config (or reference them), keeping `watcher` pointed at the
#      deployed watcher_daemon.py.
#   2. Import this module from the dev-cx53 host (the same imports list that
#      includes revdev.nix).
#   3. `sudo nixos-rebuild switch --flake .#dev-cx53` ON THE BOX.
#   4. Verify: `systemctl is-active oracle-ebpf-watcher` (active) and
#      `ls -l /run/oracle-watcher.sock` (srw-rw---- root oracle-watcher).
```

### Concrete steps for the operator

1. **Copy the files.** On dev-cx53 (or from a checkout of vaked-base), place
   `tools/oracle/oracle-ebpf-watcher.nix` and `tools/oracle/watcher_daemon.py`
   into the nix-base host config directory for dev-cx53:
   ```bash
   # from a vaked-base checkout on dev-cx53
   cp tools/oracle/oracle-ebpf-watcher.nix \
      ~/src/nix-base/hosts/dev-cx53/oracle-ebpf-watcher.nix
   cp tools/oracle/watcher_daemon.py \
      ~/src/nix-base/hosts/dev-cx53/watcher_daemon.py
   ```
   Update the `watcher = ./watcher_daemon.py;` let-binding in the `.nix` file
   if the paths differ.

2. **Import in the host config.** In the dev-cx53 `configuration.nix` (or
   wherever host-specific modules are listed), add:
   ```nix
   imports = [
     ./revdev.nix          # existing
     ./oracle-ebpf-watcher.nix   # ← add this
   ];
   ```

3. **Create the group** (if not already done by the module). NixOS will create
   `oracle-watcher` automatically via the systemd `RuntimeDirectory` + `Group`
   directives, but a persistent group for revdev membership may need:
   ```nix
   users.groups.oracle-watcher = {};
   users.users.revdev.extraGroups = [ "oracle-watcher" ];
   ```
   This lets `revdev` open `/run/oracle-watcher.sock` (which is `srw-rw----
   root oracle-watcher`).

4. **Rebuild.**
   ```bash
   sudo nixos-rebuild switch --flake .#dev-cx53
   ```

5. **Verify.**
   ```bash
   systemctl is-active oracle-ebpf-watcher   # → active
   ls -l /run/oracle-watcher.sock            # → srw-rw---- root oracle-watcher
   id revdev                                 # → groups include oracle-watcher
   ```

6. **Smoke-test the socket** (as revdev):
   ```bash
   python3 - <<'EOF'
   import sys; sys.path.insert(0, "tools/oracle")
   import watcher_client as wc
   result = wc.query_watcher("/run/oracle-watcher.sock", pid=1, duration_s=2)
   print(result)
   EOF
   # → {"syscalls": {…}, "mmaps": [], "files": []}
   ```
   PID 1 (systemd) is always running, so the query returns real data immediately.

### Why the separation is permanent

nix-base and vaked-base have independent release cadences and different
ownership boundaries. The oracle module lives in vaked-base because its
development (iteration on the bpftrace program, socket schema, group
permissions) happens alongside the oracle Python code. When the module
stabilizes it moves to nix-base as a first-class module with its own
NixOS options — that migration is a later cycle.

Until then, the manual copy-and-import procedure is the deploy path. Any
change to `oracle-ebpf-watcher.nix` or `watcher_daemon.py` in vaked-base
requires a manual redeploy on dev-cx53 following the steps above.

# 0013 — Traversable Execution: `lifecycle` block for `parallel` / `fiber`

## §1 Status

Seed draft. Grammar: v0.4. vakedc parser: complete (`LifecycleDecl` / `OnClause`
AST nodes + recursive-descent methods). Checker and emitter: not yet started.

## §2 Summary

The parallel supervision tree should be traversable and controllable. A
`lifecycle` block in a `parallel` or `fiber` declaration allows the author to
declare named control points: `pause`, `resume`, `stop`, and `rewind`. These are
**pure declarations** (no imperative side effects); they describe *when* a control
event is valid and *what parameters govern* the transition. The OTP supervisor
materializes them as process lifecycle hooks.

## §3 Concepts

### Traversable tree

The OTP supervision tree is a tree of fibers. "Traversable" means each node is
addressable by path (e.g. `parallel."operator-runtime".fiber.mediaCompress`) and
the runtime can walk the tree to deliver lifecycle events top-down or targeted at
a specific node.

### `pause`

Suspend execution at the named node. In-flight work drains up to `drain_timeout`
before the node transitions to `paused`; new work is rejected during the drain and
while paused. Child fibers receive a cascading pause if the supervisor policy
requires it.

### `resume`

Resume from `paused` state. The node transitions back to `running`; the supervisor
restores the work queue. An empty `on resume {}` record is valid and means "resume
with no additional parameters".

### `stop`

Graceful shutdown. The node drains in-flight work, optionally emits final
artifacts (`flush`, `emit_final`), and terminates. Not restartable inline; the
supervisor restart policy governs whether the process is re-spawned.

### `rewind`

Roll back to a prior checkpoint. Requires the enclosing `fiber` or `parallel` to
reference an input stream with `retention` set (so that past events are
replayable). The checker validates this and emits a hard error for `on rewind` in
declarations that lack retention. **Deferred to post-v0**: stream snapshot support
is not yet designed.

## §4 Grammar

Version v0.4 of `vaked/grammar/vaked-v0-plus.ebnf` adds:

```ebnf
lifecycle_decl  = "lifecycle" "{" { on_clause } "}" ;
on_clause       = "on" lifecycle_event record ;
lifecycle_event = "pause" | "resume" | "stop" | "rewind" ;
```

`lifecycle_decl` is the **first** alternative in `stmt`, before `field_decl`.
`lifecycle` is a soft keyword: self-disambiguating because no existing stmt begins
with `lifecycle`. `on` inside the lifecycle block is likewise soft — it is always
followed by one of the four `lifecycle_event` terminals.

`lifecycle` blocks are grammatically legal in any `block`, but the checker rejects
them outside `parallel` / `fiber` (same pattern as `field_decl` meaningful only
in `schema`).

### Usage in a `fiber`

```vaked
fiber mediaCompress {
  engine = zigimg
  input  = stream.screenrec
  output = artifacts.compressedMedia

  lifecycle {
    on pause  { drain_timeout = "2s" }
    on resume { }
    on stop   { flush = true }
  }
}
```

### Usage in a `parallel`

```vaked
parallel "operator-runtime" {
  fibers = [mediaCompress, ebpfIngest]

  strategy   = "supervised-dag"
  supervisor = otp

  lifecycle {
    on pause  { drain_timeout = "5s"  notify = "ops-channel" }
    on resume { }
    on stop   { flush = true  emit_final = true }
  }
}
```

## §5 Output-first

What artifacts does a `lifecycle` block lower to?

| Projection | Artifact |
|---|---|
| **OTP** | Lifecycle blocks lower to OTP process lifecycle callbacks in generated supervisor / worker modules. Each `on_clause` becomes a callback function (`handle_pause/2`, `handle_resume/2`, `handle_stop/2`). Parameters from the `record` body are passed as the callback's option map. |
| **Zig daemon config** | A `lifecycle` section is emitted in the generated JSON config for each Zig worker daemon, declaring the allowed control events and their parameters. |
| **Docs** | A lifecycle event table is appended per parallel group in the generated `RUNTIME.md`, listing each declared event, its parameters, and whether it cascades to child fibers. |
| **`rewind` deferred** | The `rewind` event is parsed and type-checked but is not lowered in v0. Lowering requires stream snapshot / retention support that is not yet designed. The emitter emits a `TODO` comment in generated output and a warning diagnostic. |

## §6 Determinism

Lifecycle declarations are **side-effect-free at evaluation time**. They are pure
annotations on the supervision tree; no I/O is performed during compilation. The
OTP materializer consumes the declarations and orders the lifecycle callback
registrations deterministically. Two compilations of the same source must produce
byte-identical output (upheld by the existing lowering determinism tests).

## §7 v0 boundary

| Event | v0 target | Notes |
|---|---|---|
| `pause` | yes | Drain + reject; `drain_timeout` parameter |
| `resume` | yes | No required parameters |
| `stop` | yes | Drain + optional `flush` / `emit_final` |
| `rewind` | **post-v0** | Requires stream `retention`; checker validates presence, emitter defers |

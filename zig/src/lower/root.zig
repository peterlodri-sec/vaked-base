//! vaked-lower — the 0012 lowering pass (Phase 4). Root of the `vaked-lower`
//! build module so its files stay within their own subtree (Zig 0.16 module
//! boundaries). Depends on `vaked-core` (LPG model + Value + canonical JSON) and
//! `vaked-parse` (AST, for the policy-block enrichment). Re-exported by the CLI.
//!
//! Faithful port of `vakedc/lower.py`: a pure function of a validated graph (+
//! the parsed AST items, for `enrichGraph`) → an artifact tree + a provenance
//! manifest. SQLite is out of scope (the `catalog.sqlite` target is a deferred
//! no-op, exactly as in Python's fixture set).

pub const lower_mod = @import("lower.zig");
pub const lower = lower_mod.lower;
pub const LowerResult = lower_mod.LowerResult;
pub const LowerError = lower_mod.LowerError;
pub const provenanceJsonText = lower_mod.provenanceJsonText;

test {
    _ = @import("lower.zig");
}

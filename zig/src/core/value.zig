//! `Value` — the JSON-value tree used for node/edge `props` (and, later, any
//! prop-shaped data). Mirrors what Python builds as plain dict/list/str/num/
//! bool/None. `json_canon.zig` (Task 0.4) serializes it canonically: object
//! keys sorted, lists in order, UTF-8 passthrough.
//!
//! `object` fields are stored in the order produced; the canonical writer sorts
//! keys at emit time, so insertion order here is irrelevant to output bytes.

pub const Value = union(enum) {
    null,
    bool: bool,
    int: i64,
    float: f64,
    string: []const u8,
    array: []const Value,
    object: []const Field,

    pub const Field = struct {
        key: []const u8,
        value: Value,
    };
};

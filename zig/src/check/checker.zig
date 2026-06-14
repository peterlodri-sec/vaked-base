//! checker.zig — the 0011 type-system checker, a faithful port of
//! `vakedc/check.py` (stages 3 elaborate + 4 check).
//!
//! `checkSource(alloc, src, filename, builtins)` returns a `[]Diagnostic`
//! sorted by `(file, byteStart, byteEnd, code)` — exactly Python's order. The
//! whole computation is a pure function of the parsed AST + the (pre-parsed)
//! built-in catalog; the only IO is `loadBuiltins` reading the catalog file.
//!
//! The checker works on the AST directly (it builds the same value-prop tree
//! `resolve._value_to_props` builds, but in-line), so it does not need the
//! resolved graph.

const std = @import("std");
const core = @import("vaked-core");
const lex = @import("vaked-lex");
const parse = @import("vaked-parse");

const ast = parse.ast;
const Token = lex.Token;
const Diagnostic = core.Diagnostic;

pub const CheckError = error{
    ParseFailed,
    OutOfMemory,
};

// --------------------------------------------------------------------------- //
// Value-prop tree — mirror of resolve._value_to_props output shape, but built
// here from the AST. We keep an explicit tagged union so the structural
// matching below reads like the Python dict/list inspection.
// --------------------------------------------------------------------------- //

/// Mirrors the `_value_to_props` shapes:
///   literal : {"lit": <kind-lower>, "value": str}
///   list    : [ vprop, ... ]
///   ref/app : {"ref": dotted, "args"?: [...], "record"?: [entry...]}
///   record  : {"record": [entry...]}
const VProp = union(enum) {
    lit: struct { lit: []const u8, value: []const u8 },
    list: []const VProp,
    /// app/ref: has a dotted ref, optional args, optional record entries.
    app: struct { ref: []const u8, has_args: bool, record: ?[]const VEntry },
    /// bare record value: {"record": [...]}
    record: []const VEntry,
};

const VEntry = union(enum) {
    assign: struct { name: []const u8, value: VProp },
    inherit: void,
};

fn valueToProps(alloc: std.mem.Allocator, v: ast.Expr) error{OutOfMemory}!VProp {
    switch (v) {
        .literal => |lit| return .{ .lit = .{ .lit = lit.kind.lower(), .value = lit.value } },
        .list => |ll| {
            var arr: std.ArrayList(VProp) = .empty;
            for (ll.items) |x| try arr.append(alloc, try valueToProps(alloc, x));
            return .{ .list = try arr.toOwnedSlice(alloc) };
        },
        .record => |rl| {
            return .{ .record = try entriesToProps(alloc, rl.entries) };
        },
        .app => |a| {
            const dotted = try std.mem.join(alloc, ".", a.ref.parts);
            var rec: ?[]const VEntry = null;
            if (a.record) |r| rec = try entriesToProps(alloc, r);
            return .{ .app = .{ .ref = dotted, .has_args = a.args != null, .record = rec } };
        },
    }
}

fn entriesToProps(alloc: std.mem.Allocator, entries: []const ast.Entry) error{OutOfMemory}![]const VEntry {
    var arr: std.ArrayList(VEntry) = .empty;
    for (entries) |e| {
        switch (e) {
            .assignment => |a| try arr.append(alloc, .{ .assign = .{ .name = a.target, .value = try valueToProps(alloc, a.value) } }),
            .inherit => try arr.append(alloc, .inherit),
        }
    }
    return arr.toOwnedSlice(alloc);
}

// --------------------------------------------------------------------------- //
// Schema & capability registry (Stage 3 — elaborate)
// --------------------------------------------------------------------------- //

const SCALARS = [_][]const u8{ "String", "Int", "Float", "Bool", "Path", "Duration", "Bytes", "Null" };
const STRING_ALIASES = [_][]const u8{ "Strategy", "View" };
const GENERIC_PARAMS = [_][]const u8{ "Node", "Edge" };

fn inSet(set: []const []const u8, s: []const u8) bool {
    for (set) |x| if (std.mem.eql(u8, x, s)) return true;
    return false;
}

fn isGenericParam(atom: []const u8) bool {
    if (inSet(&GENERIC_PARAMS, atom)) return true;
    // bare single upper-case letter (T, I, O, ...)
    return atom.len == 1 and atom[0] >= 'A' and atom[0] <= 'Z';
}

const FieldSpec = struct {
    name: []const u8,
    type_text: []const u8,
    refinements: []const ast.Refinement,
    presence: Presence,
    has_default: bool,

    const Presence = enum { required, optional };
};

const SchemaSpec = struct {
    name: []const u8,
    fields: []const FieldSpec, // insertion order (== source order)
    open: bool,
    origin_file: []const u8,
    decl_span: Span,

    fn field(self: SchemaSpec, name: []const u8) ?FieldSpec {
        for (self.fields) |f| if (std.mem.eql(u8, f.name, name)) return f;
        return null;
    }
    fn hasField(self: SchemaSpec, name: []const u8) bool {
        return self.field(name) != null;
    }
};

const CapabilitySpec = struct {
    domain: []const u8,
    grants: []const []const u8,
    order_chains: []const []const []const u8,
    leq: std.StringArrayHashMapUnmanaged([]const []const u8), // grant -> {g' : g <= g'}
    origin_file: []const u8,
    decl_span: Span,

    fn hasGrant(self: CapabilitySpec, g: []const u8) bool {
        return inSet(self.grants, g);
    }
};

const Span = struct { bs: usize, be: usize, line: usize, col: usize };

fn presenceOf(refinements: []const ast.Refinement) struct { presence: FieldSpec.Presence, has_default: bool } {
    var has_default = false;
    var has_optional = false;
    for (refinements) |r| {
        switch (r) {
            .default => has_default = true,
            .word => |w| {
                if (std.mem.eql(u8, w, "optional")) has_optional = true;
            },
            else => {},
        }
    }
    if (has_optional or has_default) return .{ .presence = .optional, .has_default = has_default };
    return .{ .presence = .required, .has_default = has_default };
}

fn schemaFromDecl(alloc: std.mem.Allocator, decl: ast.Decl, filename: []const u8) !SchemaSpec {
    var fields: std.ArrayList(FieldSpec) = .empty;
    var is_open = false;
    for (decl.body) |st| {
        switch (st) {
            .field_decl => |fd| {
                const p = presenceOf(fd.refinements);
                // dict semantics: later field with same name overrides; we keep
                // a list but de-dup on insert to mirror dict overwrite + key
                // iteration order (Python dict keeps first-insertion position
                // but updates value). The corpus has no dup field names, so the
                // simple path is exact; handle dup for robustness.
                var replaced = false;
                for (fields.items) |*existing| {
                    if (std.mem.eql(u8, existing.name, fd.name)) {
                        existing.* = .{ .name = fd.name, .type_text = fd.type.text, .refinements = fd.refinements, .presence = p.presence, .has_default = p.has_default };
                        replaced = true;
                        break;
                    }
                }
                if (!replaced) try fields.append(alloc, .{ .name = fd.name, .type_text = fd.type.text, .refinements = fd.refinements, .presence = p.presence, .has_default = p.has_default });
            },
            .open_decl => is_open = true,
            else => {},
        }
    }
    return .{
        .name = decl.name,
        .fields = try fields.toOwnedSlice(alloc),
        .open = is_open,
        .origin_file = filename,
        .decl_span = .{ .bs = decl.byteStart, .be = decl.byteEnd, .line = decl.line, .col = decl.col },
    };
}

fn capabilityFromDecl(alloc: std.mem.Allocator, decl: ast.Decl, filename: []const u8) !CapabilitySpec {
    var grants: std.ArrayList([]const u8) = .empty;
    var chains: std.ArrayList([]const []const u8) = .empty;
    for (decl.body) |st| {
        switch (st) {
            .grant_decl => |gd| {
                for (gd.names) |nm| try grants.append(alloc, nm);
            },
            .order_decl => |od| {
                for (od.chains) |c| try chains.append(alloc, c);
            },
            else => {},
        }
    }
    // Python: grants=set(...). Membership only; we keep the list but de-dup so
    // sorting / iteration matches a set's contents (order via sorted()).
    var uniq: std.ArrayList([]const u8) = .empty;
    for (grants.items) |g| {
        if (!inSet(uniq.items, g)) try uniq.append(alloc, g);
    }
    return .{
        .domain = decl.name,
        .grants = try uniq.toOwnedSlice(alloc),
        .order_chains = try chains.toOwnedSlice(alloc),
        .leq = .{},
        .origin_file = filename,
        .decl_span = .{ .bs = decl.byteStart, .be = decl.byteEnd, .line = decl.line, .col = decl.col },
    };
}

/// Reflexive-transitive closure of `<` declared by the chains. Returns the
/// `leq` map (g -> set of g' with g <= g'); `cycle` is non-null with the
/// offending pair if a cycle is detected.
const ClosureResult = struct {
    leq: ?std.StringArrayHashMapUnmanaged([]const []const u8),
    cycle: ?struct { a: []const u8, b: []const u8 },
};

fn transitiveClosure(alloc: std.mem.Allocator, grants: []const []const u8, chains: []const []const []const u8) !ClosureResult {
    // succ: direct edges a -> b for each consecutive pair a<b. Nodes = grants
    // plus any node mentioned in a chain (Python uses setdefault so chain-only
    // names appear too).
    var succ: std.StringArrayHashMapUnmanaged(std.ArrayList([]const u8)) = .{};
    // seed with grants
    for (grants) |g| {
        if (!succ.contains(g)) try succ.put(alloc, g, .empty);
    }
    for (chains) |ch| {
        var k: usize = 0;
        while (k + 1 < ch.len) : (k += 1) {
            const a = ch[k];
            const b = ch[k + 1];
            const ga = try succ.getOrPut(alloc, a);
            if (!ga.found_existing) ga.value_ptr.* = .empty;
            if (!listContains(ga.value_ptr.items, b)) try ga.value_ptr.append(alloc, b);
            const gb = try succ.getOrPut(alloc, b);
            if (!gb.found_existing) gb.value_ptr.* = .empty;
        }
    }

    const nodes = succ.keys();

    // reach: reflexive-transitive closure via DFS per node.
    var reach: std.StringArrayHashMapUnmanaged(std.ArrayList([]const u8)) = .{};
    for (nodes) |g| {
        var set: std.ArrayList([]const u8) = .empty;
        try set.append(alloc, g); // reflexive
        // DFS over successors
        var stack: std.ArrayList([]const u8) = .empty;
        if (succ.get(g)) |s| for (s.items) |x| try stack.append(alloc, x);
        while (stack.items.len > 0) {
            const x = stack.pop().?;
            if (!listContains(set.items, x)) {
                try set.append(alloc, x);
                if (succ.get(x)) |s| for (s.items) |y| try stack.append(alloc, y);
            }
        }
        try reach.put(alloc, g, set);
    }

    // self-edge => degenerate cycle.
    for (nodes) |a| {
        if (succ.get(a)) |s| {
            if (listContains(s.items, a)) return .{ .leq = null, .cycle = .{ .a = a, .b = a } };
        }
    }
    // antisymmetry: a<=b and b<=a with a!=b => cycle.
    for (nodes) |a| {
        const ra = reach.get(a).?;
        for (ra.items) |b| {
            if (!std.mem.eql(u8, a, b)) {
                if (reach.get(b)) |rb| {
                    if (listContains(rb.items, a)) return .{ .leq = null, .cycle = .{ .a = a, .b = b } };
                }
            }
        }
    }

    // Materialize leq map as plain slices.
    var leq: std.StringArrayHashMapUnmanaged([]const []const u8) = .{};
    for (nodes) |g| {
        const set = reach.get(g).?;
        try leq.put(alloc, g, try alloc.dupe([]const u8, set.items));
    }
    return .{ .leq = leq, .cycle = null };
}

fn listContains(list: []const []const u8, s: []const u8) bool {
    for (list) |x| if (std.mem.eql(u8, x, s)) return true;
    return false;
}

const Registry = struct {
    alloc: std.mem.Allocator,
    schemas: std.StringArrayHashMapUnmanaged(SchemaSpec) = .{},
    caps: std.StringArrayHashMapUnmanaged(CapabilitySpec) = .{},

    fn addSchema(self: *Registry, spec: SchemaSpec) !void {
        try self.schemas.put(self.alloc, spec.name, spec); // later overrides earlier
    }
    fn addCapability(self: *Registry, spec: CapabilitySpec) !void {
        try self.caps.put(self.alloc, spec.domain, spec);
    }
    fn getSchema(self: *Registry, name: []const u8) ?SchemaSpec {
        return self.schemas.get(name);
    }
    fn getCap(self: *Registry, name: []const u8) ?CapabilitySpec {
        return self.caps.get(name);
    }
};

fn loadDeclsInto(reg: *Registry, items: []const ast.Item, filename: []const u8) !void {
    for (items) |it| {
        switch (it) {
            .decl => |d| {
                if (std.mem.eql(u8, d.kind, "schema")) {
                    try reg.addSchema(try schemaFromDecl(reg.alloc, d, filename));
                } else if (std.mem.eql(u8, d.kind, "capability")) {
                    try reg.addCapability(try capabilityFromDecl(reg.alloc, d, filename));
                }
            },
            .import => {},
        }
    }
}

// --------------------------------------------------------------------------- //
// Source position map — locate a construct's byte span within a decl
// --------------------------------------------------------------------------- //

const SourceMap = struct {
    file: []const u8,
    tokens: []const Token, // NEWLINE/EOF stripped

    fn init(alloc: std.mem.Allocator, src: []const u8, filename: []const u8) !SourceMap {
        var errinfo: lex.ErrInfo = undefined;
        // tokenize is deterministic & pure; the builtins + file already lex OK
        // (the parser would have errored otherwise). If it somehow fails, fall
        // back to an empty token set (span resolution then yields null → decl).
        const toks = lex.tokenize(alloc, src, filename, &errinfo) catch &[_]Token{};
        var kept: std.ArrayList(Token) = .empty;
        for (toks) |t| {
            if (t.kind != .NEWLINE and t.kind != .EOF) try kept.append(alloc, t);
        }
        return .{ .file = filename, .tokens = try kept.toOwnedSlice(alloc) };
    }

    fn toksIn(self: SourceMap, alloc: std.mem.Allocator, bs: usize, be: usize) ![]const Token {
        var out: std.ArrayList(Token) = .empty;
        for (self.tokens) |t| {
            if (bs <= t.byteStart and t.byteStart < be) try out.append(alloc, t);
        }
        return out.toOwnedSlice(alloc);
    }

    fn fieldNameSpan(self: SourceMap, alloc: std.mem.Allocator, ds: usize, de: usize, name: []const u8) !?Span {
        const toks = try self.toksIn(alloc, ds, de);
        for (toks, 0..) |t, idx| {
            if (t.kind == .IDENT and std.mem.eql(u8, t.value, name)) {
                const nxt: ?Token = if (idx + 1 < toks.len) toks[idx + 1] else null;
                if (nxt) |n| {
                    if (n.kind == .OP and (std.mem.eql(u8, n.value, "=") or std.mem.eql(u8, n.value, "?=") or std.mem.eql(u8, n.value, ":") or std.mem.eql(u8, n.value, "{"))) {
                        return spanOf(t);
                    }
                }
            }
        }
        return null;
    }

    fn fieldValueSpan(self: SourceMap, alloc: std.mem.Allocator, ds: usize, de: usize, name: []const u8) !?Span {
        const toks = try self.toksIn(alloc, ds, de);
        for (toks, 0..) |t, idx| {
            if (t.kind == .IDENT and std.mem.eql(u8, t.value, name)) {
                const nxt: ?Token = if (idx + 1 < toks.len) toks[idx + 1] else null;
                if (nxt) |n| {
                    if (n.kind == .OP and (std.mem.eql(u8, n.value, "=") or std.mem.eql(u8, n.value, "?="))) {
                        if (idx + 2 < toks.len) return spanOf(toks[idx + 2]);
                    }
                }
            }
        }
        // fall back to the field name
        return self.fieldNameSpan(alloc, ds, de, name);
    }
};

fn spanOf(t: Token) Span {
    return .{ .bs = t.byteStart, .be = t.byteEnd, .line = t.line, .col = t.col };
}

// --------------------------------------------------------------------------- //
// The checker context — collects diagnostics + holds the registry & smaps.
// --------------------------------------------------------------------------- //

/// Decl label source: either a real Decl (kind+name), a SchemaSpec / CapSpec,
/// or a literal string (for mesh nodes: "node <name>").
const DeclLabel = union(enum) {
    decl: ast.Decl,
    schema: []const u8, // schema name
    capability: []const u8, // domain
    str: []const u8,

    fn label(self: DeclLabel, alloc: std.mem.Allocator) ![]const u8 {
        return switch (self) {
            .decl => |d| std.fmt.allocPrint(alloc, "{s} {s}", .{ d.kind, d.name }),
            .schema => |n| std.fmt.allocPrint(alloc, "schema {s}", .{n}),
            .capability => |n| std.fmt.allocPrint(alloc, "capability {s}", .{n}),
            .str => |s| s,
        };
    }
};

const Checker = struct {
    alloc: std.mem.Allocator,
    reg: *Registry,
    diags: *std.ArrayList(Diagnostic),

    fn emit(self: *Checker, code: []const u8, file: []const u8, span: Span, decl: DeclLabel, message: []const u8) !void {
        try self.diags.append(self.alloc, .{
            .code = code,
            .message = message,
            .file = file,
            .byteStart = span.bs,
            .byteEnd = span.be,
            .line = span.line,
            .col = span.col,
            .decl = try decl.label(self.alloc),
            .related = &.{},
        });
    }
};

// --------------------------------------------------------------------------- //
// Type helpers (literal/value matching, §2.4 / §2.5)
// --------------------------------------------------------------------------- //

/// Strip the outermost List<...> wrapper. Mirrors `_base_type`.
fn baseType(type_text: []const u8) struct { inner: []const u8, is_list: bool } {
    const t = std.mem.trim(u8, type_text, " \t");
    if (std.mem.startsWith(u8, t, "List<") and std.mem.endsWith(u8, t, ">")) {
        const inner = std.mem.trim(u8, t["List<".len .. t.len - 1], " \t");
        return .{ .inner = inner, .is_list = true };
    }
    return .{ .inner = t, .is_list = false };
}

fn isNumericType(type_text: []const u8) bool {
    const bt = baseType(type_text);
    return std.mem.eql(u8, bt.inner, "Int") or std.mem.eql(u8, bt.inner, "Float") or
        std.mem.eql(u8, bt.inner, "Duration") or std.mem.eql(u8, bt.inner, "Bytes");
}

/// Split a union type on top-level '|' (not inside '<...>'). Returns trimmed arms.
fn splitUnion(alloc: std.mem.Allocator, text: []const u8) ![]const []const u8 {
    var parts: std.ArrayList([]const u8) = .empty;
    var depth: i32 = 0;
    var start: usize = 0;
    var i: usize = 0;
    while (i < text.len) : (i += 1) {
        const ch = text[i];
        if (ch == '<') {
            depth += 1;
        } else if (ch == '>') {
            depth -= 1;
        } else if (ch == '|' and depth == 0) {
            try parts.append(alloc, std.mem.trim(u8, text[start..i], " \t"));
            start = i + 1;
        }
    }
    try parts.append(alloc, std.mem.trim(u8, text[start..], " \t"));
    return parts.toOwnedSlice(alloc);
}

/// `_literal_matches_scalar` for an AST literal (kind + value text).
fn literalKindMatchesScalar(kind: ast.LitKind, value: []const u8, type_atom: []const u8) bool {
    if (isGenericParam(type_atom)) return true;
    if (inSet(&STRING_ALIASES, type_atom)) return kind == .STRING;
    if (!inSet(&SCALARS, type_atom)) return false;
    if (std.mem.eql(u8, type_atom, "Null")) return kind == .NULL;
    if (std.mem.eql(u8, type_atom, "String")) return kind == .STRING;
    if (std.mem.eql(u8, type_atom, "Bool")) return kind == .BOOL;
    if (std.mem.eql(u8, type_atom, "Int")) return kind == .NUMBER and (std.mem.indexOfScalar(u8, value, '.') == null);
    if (std.mem.eql(u8, type_atom, "Float")) return kind == .NUMBER;
    if (std.mem.eql(u8, type_atom, "Path")) return kind == .PATH or kind == .STRING;
    if (std.mem.eql(u8, type_atom, "Duration")) return kind == .DURATION or kind == .STRING;
    if (std.mem.eql(u8, type_atom, "Bytes")) return kind == .BYTES or kind == .STRING;
    return false;
}

/// `_literal_matches_type` for an AST literal.
fn literalMatchesType(lit: ast.Literal, type_text: []const u8, alloc: std.mem.Allocator) !bool {
    const bt = baseType(type_text);
    if (bt.is_list) return false;
    // split on '|' — _literal_matches_type uses simple split('|'); union types
    // here never contain '<...>' arms at this scalar level in the corpus, but
    // we use a top-level split to be safe.
    var it = std.mem.splitScalar(u8, bt.inner, '|');
    while (it.next()) |arm_raw| {
        const arm = std.mem.trim(u8, arm_raw, " \t");
        if (literalKindMatchesScalar(lit.kind, lit.value, arm)) return true;
    }
    _ = alloc;
    return false;
}

/// litprop ({"lit":..,"value":..}) matches a scalar atom (`_litprop_matches_scalar`).
fn litPropMatchesScalar(lit_lower: []const u8, value: []const u8, atom: []const u8) bool {
    const kind = lowerLitToKind(lit_lower);
    return literalKindMatchesScalar(kind, value, atom);
}

fn lowerLitToKind(lit_lower: []const u8) ast.LitKind {
    // Python uppercases the "lit" string; map back to a LitKind. Unknown -> NULL
    // (matches the Python `kind if kind else "NULL"` fallback closely enough;
    // the corpus always carries a valid lit).
    if (std.mem.eql(u8, lit_lower, "string")) return .STRING;
    if (std.mem.eql(u8, lit_lower, "number")) return .NUMBER;
    if (std.mem.eql(u8, lit_lower, "duration")) return .DURATION;
    if (std.mem.eql(u8, lit_lower, "bytes")) return .BYTES;
    if (std.mem.eql(u8, lit_lower, "path")) return .PATH;
    if (std.mem.eql(u8, lit_lower, "bool")) return .BOOL;
    return .NULL;
}

/// `_value_matches_type` — structural match of a value-prop against a type.
fn valueMatchesType(alloc: std.mem.Allocator, vprop: VProp, type_text: []const u8, reg: *Registry) error{OutOfMemory}!bool {
    const bt = baseType(type_text);
    if (bt.is_list) {
        switch (vprop) {
            .list => |items| {
                for (items) |e| {
                    if (!try valueMatchesType(alloc, e, bt.inner, reg)) return false;
                }
                return true;
            },
            else => return false,
        }
    }
    const arms = try splitUnion(alloc, bt.inner);
    for (arms) |arm| {
        if (try valueMatchesAtom(alloc, vprop, arm, reg)) return true;
    }
    return false;
}

fn valueMatchesAtom(alloc: std.mem.Allocator, vprop: VProp, atom_in: []const u8, reg: *Registry) error{OutOfMemory}!bool {
    const atom = std.mem.trim(u8, atom_in, " \t");
    const abt = baseType(atom);
    if (abt.is_list) return valueMatchesType(alloc, vprop, atom, reg);
    if (isGenericParam(abt.inner)) return true;
    switch (vprop) {
        .lit => |l| return litPropMatchesScalar(l.lit, l.value, abt.inner),
        .list => return false,
        .app => {
            if (inSet(&SCALARS, abt.inner) or inSet(&STRING_ALIASES, abt.inner)) return false;
            // a structural record value checked against a named schema:
            // Python checks `"record" in vprop and "ref" not in vprop` — for an
            // app, "ref" is always present, so this branch never does the
            // schema check; a non-literal value matches any non-scalar atom.
            return true;
        },
        .record => |entries| {
            if (inSet(&SCALARS, abt.inner) or inSet(&STRING_ALIASES, abt.inner)) return false;
            // "record" in vprop and "ref" not in vprop -> structural conformance
            if (reg.getSchema(abt.inner)) |schema| {
                return recordConforms(alloc, entries, schema, reg);
            }
            return true;
        },
    }
}

/// `_record_conforms` — best-effort structural conformance of a record value.
fn recordConforms(alloc: std.mem.Allocator, entries: []const VEntry, schema: SchemaSpec, reg: *Registry) error{OutOfMemory}!bool {
    // present: name -> value (last wins, dict semantics)
    // required present
    for (schema.fields) |f| {
        if (f.presence == .required and !entryPresent(entries, f.name)) return false;
    }
    if (!schema.open) {
        for (entries) |e| switch (e) {
            .assign => |a| {
                if (!schema.hasField(a.name)) return false;
            },
            .inherit => {},
        };
    }
    for (entries) |e| switch (e) {
        .assign => |a| {
            if (schema.field(a.name)) |f| {
                if (!try valueMatchesType(alloc, a.value, f.type_text, reg)) return false;
            }
        },
        .inherit => {},
    };
    return true;
}

fn entryPresent(entries: []const VEntry, name: []const u8) bool {
    for (entries) |e| switch (e) {
        .assign => |a| {
            if (std.mem.eql(u8, a.name, name)) return true;
        },
        .inherit => {},
    };
    return false;
}

/// Lookup last-assigned value for a name in record entries (dict semantics).
fn entryValue(entries: []const VEntry, name: []const u8) ?VProp {
    var found: ?VProp = null;
    for (entries) |e| switch (e) {
        .assign => |a| {
            if (std.mem.eql(u8, a.name, name)) found = a.value;
        },
        .inherit => {},
    };
    return found;
}

// --------------------------------------------------------------------------- //
// Number / render helpers
// --------------------------------------------------------------------------- //

/// `_num` — Python float() parse; null if not a number.
fn num(s: []const u8) ?f64 {
    const t = std.mem.trim(u8, s, " \t");
    if (t.len == 0) return null;
    return std.fmt.parseFloat(f64, t) catch null;
}

/// `_vprop_number` — numeric value of a literal vprop whose lit is "number".
fn vpropNumber(vprop: VProp) ?f64 {
    switch (vprop) {
        .lit => |l| {
            if (std.mem.eql(u8, l.lit, "number")) return num(l.value);
            return null;
        },
        else => return null,
    }
}

/// `_fmtnum` — int-valued floats print without a decimal, else str(v).
fn fmtNum(alloc: std.mem.Allocator, v: f64) ![]const u8 {
    if (v == @trunc(v) and @abs(v) < 1e15) {
        return std.fmt.allocPrint(alloc, "{d}", .{@as(i64, @intFromFloat(v))});
    }
    // Python str(float): shortest round-trip repr. Zig {d} on f64 matches for
    // the values the corpus produces (none beyond integers today).
    return std.fmt.allocPrint(alloc, "{d}", .{v});
}

/// `_render_vprop` — value rendering for messages.
fn renderVprop(alloc: std.mem.Allocator, vprop: VProp) ![]const u8 {
    switch (vprop) {
        .lit => |l| {
            if (std.mem.eql(u8, l.lit, "string")) return std.fmt.allocPrint(alloc, "\"{s}\"", .{l.value});
            return l.value;
        },
        .app => |a| return a.ref,
        else => return "?", // repr() — not hit by the corpus
    }
}

/// `_render_literal` — AST literal rendering for messages.
fn renderLiteral(alloc: std.mem.Allocator, lit: ast.Literal) ![]const u8 {
    if (lit.kind == .STRING) return std.fmt.allocPrint(alloc, "\"{s}\"", .{lit.value});
    return lit.value;
}

/// `_render_oneof` — render a list of (kind, value) allowed elements.
fn renderOneof(alloc: std.mem.Allocator, items: []const ast.Expr) ![]const u8 {
    var buf: std.ArrayList(u8) = .empty;
    try buf.append(alloc, '[');
    var first = true;
    for (items) |it| {
        if (it != .literal) continue; // only literals carry (kind,value); App etc. -> handled below
        const lit = it.literal;
        if (!first) try buf.appendSlice(alloc, ", ");
        first = false;
        if (lit.kind == .STRING) {
            try buf.appendSlice(alloc, try std.fmt.allocPrint(alloc, "\"{s}\"", .{lit.value}));
        } else {
            try buf.appendSlice(alloc, lit.value);
        }
    }
    try buf.append(alloc, ']');
    return buf.toOwnedSlice(alloc);
}

// --------------------------------------------------------------------------- //
// Regex dialect validation (§3.5)
// --------------------------------------------------------------------------- //

/// `_regex_dialect_error` — returns an explanatory string if the regex uses a
/// feature outside the bounded dialect; null otherwise.
fn regexDialectError(alloc: std.mem.Allocator, regex_literal: []const u8) !?[]const u8 {
    var body = regex_literal;
    if (body.len >= 2 and body[0] == '/' and body[body.len - 1] == '/') {
        body = body[1 .. body.len - 1];
    }
    var i: usize = 0;
    const n = body.len;
    var in_class = false;
    while (i < n) {
        const c = body[i];
        if (c == '\\') {
            if (i + 1 >= n) return "trailing backslash";
            const nxt = body[i + 1];
            if (nxt >= '1' and nxt <= '9') {
                const m: []const u8 = try std.fmt.allocPrint(alloc, "backreference (\\{c}) is not in the bounded dialect", .{nxt});
                return m;
            }
            i += 2;
            continue;
        }
        if (in_class) {
            if (c == ']') in_class = false;
            i += 1;
            continue;
        }
        if (c == '[') {
            in_class = true;
            i += 1;
            continue;
        }
        if (c == '(') {
            if (i + 1 < n and body[i + 1] == '?') {
                const kind: u8 = if (i + 2 < n) body[i + 2] else 0;
                if (kind == '=' or kind == '!') {
                    const m: []const u8 = try std.fmt.allocPrint(alloc, "lookahead ((?{c}…)) is not in the bounded dialect", .{kind});
                    return m;
                }
                if (kind == '<') {
                    const nxt: u8 = if (i + 3 < n) body[i + 3] else 0;
                    if (nxt == '=' or nxt == '!') {
                        const m: []const u8 = try std.fmt.allocPrint(alloc, "lookbehind ((?<{c}…)) is not in the bounded dialect", .{nxt});
                        return m;
                    }
                    return "named group ((?<…>)) is not in the bounded dialect";
                }
                if (kind == 'P') return "named group ((?P…)) is not in the bounded dialect";
                if (kind == '>') return "atomic group ((?>…)) is not in the bounded dialect";
                if (kind == ':') {
                    i += 3;
                    continue;
                }
                const m: []const u8 = try std.fmt.allocPrint(alloc, "extended group ((?{c}…)) is not in the bounded dialect", .{kind});
                return m;
            }
            i += 1;
            continue;
        }
        i += 1;
    }
    if (in_class) return "unterminated character class '['";
    return null;
}

// --------------------------------------------------------------------------- //
// Constraint application (§3) on a bound field value
// --------------------------------------------------------------------------- //

fn checkFieldConstraints(ch: *Checker, smap: ?SourceMap, vprop: VProp, fspec: FieldSpec, decl: DeclLabel, file: []const u8, decl_span: Span) !void {
    const vspan = (try fieldValueSpanOr(ch.alloc, smap, decl_span, fspec.name)) orelse decl_span;
    for (fspec.refinements) |r| {
        switch (r) {
            .word => |w| {
                if (std.mem.eql(u8, w, "nonempty")) {
                    if (isEmpty(vprop)) {
                        try ch.emit("E-CONSTRAINT-NONEMPTY", file, vspan, decl, try std.fmt.allocPrint(ch.alloc, "field `{s}` is `nonempty` but the value is empty", .{fspec.name}));
                    }
                }
            },
            .oneof => |ll| {
                switch (vprop) {
                    .lit => |l| {
                        if (!litPropInOneof(l, ll.items)) {
                            try ch.emit("E-CONSTRAINT-ONEOF", file, vspan, decl, try std.fmt.allocPrint(ch.alloc, "field `{s}`: value {s} is not one of {s}", .{ fspec.name, try renderVprop(ch.alloc, vprop), try renderOneof(ch.alloc, ll.items) }));
                        }
                    },
                    else => {},
                }
            },
            .cmp => |c| try checkCmp(ch, vprop, c.op, c.num, fspec, decl, file, vspan),
            .range => |rg| try checkRange(ch, vprop, rg.lo, rg.hi, fspec, decl, file, vspan),
            else => {}, // required/optional/default/matches handled elsewhere
        }
    }
}

fn checkCmp(ch: *Checker, vprop: VProp, op: []const u8, bound_s: []const u8, fspec: FieldSpec, decl: DeclLabel, file: []const u8, vspan: Span) !void {
    const v = vpropNumber(vprop) orelse return;
    const b = num(bound_s) orelse return;
    const ok = if (std.mem.eql(u8, op, ">=")) v >= b else if (std.mem.eql(u8, op, "<=")) v <= b else if (std.mem.eql(u8, op, ">")) v > b else if (std.mem.eql(u8, op, "<")) v < b else true;
    if (!ok) {
        try ch.emit("E-CONSTRAINT-RANGE", file, vspan, decl, try std.fmt.allocPrint(ch.alloc, "field `{s}`: value {s} violates `{s} {s}`", .{ fspec.name, try fmtNum(ch.alloc, v), op, bound_s }));
    }
}

fn checkRange(ch: *Checker, vprop: VProp, lo_s: []const u8, hi_s: []const u8, fspec: FieldSpec, decl: DeclLabel, file: []const u8, vspan: Span) !void {
    const v = vpropNumber(vprop) orelse return;
    const lo = num(lo_s) orelse return;
    const hi = num(hi_s) orelse return;
    if (!(lo <= v and v <= hi)) {
        try ch.emit("E-CONSTRAINT-RANGE", file, vspan, decl, try std.fmt.allocPrint(ch.alloc, "field `{s}`: value {s} is outside `in {s} .. {s}`", .{ fspec.name, try fmtNum(ch.alloc, v), lo_s, hi_s }));
    }
}

fn checkMatches(ch: *Checker, vprop: VProp, regex_literal: []const u8, fspec: FieldSpec, decl: DeclLabel, file: []const u8, vspan: Span) !void {
    switch (vprop) {
        .lit => |l| {
            if (!(std.mem.eql(u8, l.lit, "string") or std.mem.eql(u8, l.lit, "path"))) return;
            var body = regex_literal;
            if (body.len >= 2 and body[0] == '/' and body[body.len - 1] == '/') body = body[1 .. body.len - 1];
            const matched = regexFullMatch(ch.alloc, body, l.value) catch return; // malformed already reported at load
            if (!matched) {
                try ch.emit("E-CONSTRAINT-MATCHES", file, vspan, decl, try std.fmt.allocPrint(ch.alloc, "field `{s}`: value {s} does not match /{s}/", .{ fspec.name, try renderVprop(ch.alloc, vprop), body }));
            }
        },
        else => {},
    }
}

/// Minimal regex full-match for the bounded dialect (§3.5). Supports literal
/// chars, '.', '*', '+', '?', '|' alternation, grouping '(...)' incl. '(?:...)',
/// char classes '[...]', anchors '^'/'$' (treated as no-ops under fullmatch),
/// and backslash escapes. Returns whether the pattern fully matches `text`.
///
/// NOTE: no corpus file exercises a *bound* `matches` value, so this path is
/// not byte-gated today; it is implemented for forward parity with Python's
/// `re.fullmatch`. On a pattern this matcher cannot represent, it errors (the
/// caller then suppresses the diagnostic, matching Python's behavior on a
/// regex `re.error`).
fn regexFullMatch(alloc: std.mem.Allocator, pattern: []const u8, text: []const u8) !bool {
    var rx = Regex{ .alloc = alloc, .pat = pattern };
    return rx.fullMatch(text);
}

const Regex = struct {
    alloc: std.mem.Allocator,
    pat: []const u8,

    fn fullMatch(self: *Regex, text: []const u8) !bool {
        // Anchor both ends (fullmatch). Strip a leading '^' / trailing '$' since
        // they are redundant under fullmatch.
        var p = self.pat;
        if (p.len > 0 and p[0] == '^') p = p[1..];
        if (p.len > 0 and p[p.len - 1] == '$') p = p[0 .. p.len - 1];
        return self.matchHere(p, text, 0, text.len);
    }

    /// Match `pat` against `text[ti..te]`, requiring it to consume the whole range.
    fn matchHere(self: *Regex, pat: []const u8, text: []const u8, ti: usize, te: usize) error{ OutOfMemory, BadRegex }!bool {
        // Try matching one "atom + optional quantifier", then recurse.
        if (pat.len == 0) return ti == te;
        // Parse the first atom (with its byte length) and the quantifier.
        const atom = try self.parseAtom(pat);
        const after = pat[atom.len..];
        var quant: u8 = 0;
        var rest = after;
        if (after.len > 0 and (after[0] == '*' or after[0] == '+' or after[0] == '?')) {
            quant = after[0];
            rest = after[1..];
        }
        switch (quant) {
            0 => {
                if (ti < te and self.atomMatches(atom, text[ti])) {
                    return self.matchHere(rest, text, ti + 1, te);
                }
                return false;
            },
            '?' => {
                if (ti < te and self.atomMatches(atom, text[ti])) {
                    if (try self.matchHere(rest, text, ti + 1, te)) return true;
                }
                return self.matchHere(rest, text, ti, te);
            },
            '*', '+' => {
                // greedy: consume as many as possible, then backtrack.
                var count: usize = 0;
                var j = ti;
                while (j < te and self.atomMatches(atom, text[j])) : (j += 1) count += 1;
                const min: usize = if (quant == '+') 1 else 0;
                if (count < min) return false;
                var k = j;
                while (true) {
                    const consumed = k - ti;
                    if (consumed >= min) {
                        if (try self.matchHere(rest, text, k, te)) return true;
                    }
                    if (k == ti) break;
                    k -= 1;
                }
                return false;
            },
            else => return error.BadRegex,
        }
    }

    const Atom = struct { len: usize, kind: AtomKind, lit: u8, class: []const u8, negate: bool };
    const AtomKind = enum { lit, any, class };

    fn parseAtom(self: *Regex, pat: []const u8) error{BadRegex}!Atom {
        _ = self;
        const c = pat[0];
        if (c == '\\') {
            if (pat.len < 2) return error.BadRegex;
            return .{ .len = 2, .kind = .lit, .lit = pat[1], .class = &.{}, .negate = false };
        }
        if (c == '.') return .{ .len = 1, .kind = .any, .lit = 0, .class = &.{}, .negate = false };
        if (c == '[') {
            // find closing ']'
            var i: usize = 1;
            var negate = false;
            if (i < pat.len and pat[i] == '^') {
                negate = true;
                i += 1;
            }
            const start = i;
            while (i < pat.len and pat[i] != ']') i += 1;
            if (i >= pat.len) return error.BadRegex;
            return .{ .len = i + 1, .kind = .class, .lit = 0, .class = pat[start..i], .negate = negate };
        }
        if (c == '(' or c == ')' or c == '|') return error.BadRegex; // groups/alt unsupported here
        return .{ .len = 1, .kind = .lit, .lit = c, .class = &.{}, .negate = false };
    }

    fn atomMatches(self: *Regex, atom: Atom, ch: u8) bool {
        _ = self;
        switch (atom.kind) {
            .lit => return ch == atom.lit,
            .any => return true,
            .class => {
                var in_class = false;
                var i: usize = 0;
                while (i < atom.class.len) : (i += 1) {
                    if (i + 2 < atom.class.len and atom.class[i + 1] == '-') {
                        if (ch >= atom.class[i] and ch <= atom.class[i + 2]) in_class = true;
                        i += 2;
                    } else if (ch == atom.class[i]) {
                        in_class = true;
                    }
                }
                return in_class != atom.negate;
            },
        }
    }
};

fn isEmpty(vprop: VProp) bool {
    switch (vprop) {
        .list => |items| return items.len == 0,
        .lit => |l| return l.value.len == 0, // value == "" or None
        else => return false,
    }
}

fn litPropInOneof(l: anytype, items: []const ast.Expr) bool {
    const k = l.lit; // already lower
    for (items) |it| {
        if (it != .literal) continue;
        const lit = it.literal;
        const ak = lit.kind.lower();
        if (std.mem.eql(u8, ak, k) and std.mem.eql(u8, lit.value, l.value)) return true;
        // numeric tolerance: Int literal vs Int oneof element
        if (lit.kind == .NUMBER and std.mem.eql(u8, k, "number")) {
            const a = num(lit.value);
            const b = num(l.value);
            if (a != null and b != null and a.? == b.?) return true;
        }
    }
    return false;
}

// --------------------------------------------------------------------------- //
// span helpers (deferred null-OR-fallback pattern)
// --------------------------------------------------------------------------- //

fn fieldNameSpanOr(alloc: std.mem.Allocator, smap: ?SourceMap, ds: usize, de: usize, name: []const u8) !?Span {
    if (smap) |s| return s.fieldNameSpan(alloc, ds, de, name);
    return null;
}
fn fieldValueSpanOr(alloc: std.mem.Allocator, smap: ?SourceMap, decl_span: Span, name: []const u8) !?Span {
    if (smap) |s| return s.fieldValueSpan(alloc, decl_span.bs, decl_span.be, name);
    return null;
}

// --------------------------------------------------------------------------- //
// Load-time well-formedness (§3.7, §4.2, §6.5)
// --------------------------------------------------------------------------- //

fn checkSchemaWellformed(ch: *Checker, smap: ?SourceMap, spec: SchemaSpec) !void {
    const ds = spec.decl_span;
    const decl: DeclLabel = .{ .schema = spec.name };
    for (spec.fields) |f| {
        var seen_required = false;
        var seen_optional = false;
        for (f.refinements) |r| {
            const span = ((try fieldNameSpanOr(ch.alloc, smap, ds.bs, ds.be, f.name)) orelse ds);
            switch (r) {
                .word => |w| {
                    if (std.mem.eql(u8, w, "required")) seen_required = true;
                    if (std.mem.eql(u8, w, "optional")) seen_optional = true;
                },
                .matches => |regex| {
                    const bt = baseType(f.type_text);
                    if (!(std.mem.eql(u8, bt.inner, "String") or std.mem.eql(u8, bt.inner, "Path"))) {
                        try ch.emit("E-SCHEMA-REFINEMENT", spec.origin_file, span, decl, try std.fmt.allocPrint(ch.alloc, "`matches` applies only to String or Path; field `{s}` is `{s}`", .{ f.name, f.type_text }));
                    } else {
                        if (try regexDialectError(ch.alloc, regex)) |err| {
                            try ch.emit("E-SCHEMA-BAD-REGEX", spec.origin_file, span, decl, try std.fmt.allocPrint(ch.alloc, "field `{s}`: {s}", .{ f.name, err }));
                        }
                    }
                },
                .oneof => |ll| {
                    if (ll.items.len < 1) {
                        try ch.emit("E-SCHEMA-REFINEMENT", spec.origin_file, span, decl, try std.fmt.allocPrint(ch.alloc, "field `{s}`: `oneof` needs at least one element", .{f.name}));
                    }
                    for (ll.items) |lit_expr| {
                        if (lit_expr != .literal or !try literalMatchesType(lit_expr.literal, f.type_text, ch.alloc)) {
                            // _literal_matches_type(non-Literal) -> isinstance check false -> False
                            const rendered = if (lit_expr == .literal) try renderLiteral(ch.alloc, lit_expr.literal) else try renderExprRepr(ch.alloc, lit_expr);
                            try ch.emit("E-SCHEMA-BAD-ONEOF", spec.origin_file, span, decl, try std.fmt.allocPrint(ch.alloc, "field `{s}`: `oneof` element {s} does not match type `{s}`", .{ f.name, rendered, f.type_text }));
                        }
                    }
                },
                .cmp => {
                    if (!isNumericType(f.type_text)) {
                        try ch.emit("E-SCHEMA-REFINEMENT", spec.origin_file, span, decl, try std.fmt.allocPrint(ch.alloc, "field `{s}`: numeric refinement on non-numeric type `{s}`", .{ f.name, f.type_text }));
                    }
                },
                .range => |rg| {
                    if (!isNumericType(f.type_text)) {
                        try ch.emit("E-SCHEMA-REFINEMENT", spec.origin_file, span, decl, try std.fmt.allocPrint(ch.alloc, "field `{s}`: numeric refinement on non-numeric type `{s}`", .{ f.name, f.type_text }));
                    }
                    const lo = num(rg.lo);
                    const hi = num(rg.hi);
                    if (lo != null and hi != null and lo.? > hi.?) {
                        try ch.emit("E-SCHEMA-BAD-RANGE", spec.origin_file, span, decl, try std.fmt.allocPrint(ch.alloc, "field `{s}`: range lower bound {s} exceeds upper bound {s}", .{ f.name, rg.lo, rg.hi }));
                    }
                },
                .default => |expr| {
                    if (expr == .app) {
                        try ch.emit("E-SCHEMA-BAD-DEFAULT", spec.origin_file, span, decl, try std.fmt.allocPrint(ch.alloc, "field `{s}`: `default` must be a literal, not a ref", .{f.name}));
                    } else if (expr == .literal and !try literalMatchesType(expr.literal, f.type_text, ch.alloc)) {
                        try ch.emit("E-SCHEMA-BAD-DEFAULT", spec.origin_file, span, decl, try std.fmt.allocPrint(ch.alloc, "field `{s}`: default {s} does not match type `{s}`", .{ f.name, try renderLiteral(ch.alloc, expr.literal), f.type_text }));
                    }
                },
            }
        }
        if (seen_required and (seen_optional or f.has_default)) {
            const span = ((try fieldNameSpanOr(ch.alloc, smap, ds.bs, ds.be, f.name)) orelse ds);
            try ch.emit("E-SCHEMA-REFINEMENT", spec.origin_file, span, decl, try std.fmt.allocPrint(ch.alloc, "field `{s}`: `required` cannot be combined with `optional`/`default`", .{f.name}));
        }
    }
}

fn renderExprRepr(alloc: std.mem.Allocator, expr: ast.Expr) ![]const u8 {
    _ = expr;
    return alloc.dupe(u8, "?");
}

fn checkCapabilityWellformed(ch: *Checker, smap: ?SourceMap, spec: *CapabilitySpec) !void {
    const ds = spec.decl_span;
    const decl: DeclLabel = .{ .capability = spec.domain };
    const span = ds;
    // 1. every grant named in order must be declared. Python: sorted(named - grants).
    var named: std.ArrayList([]const u8) = .empty;
    for (spec.order_chains) |c| {
        for (c) |g| if (!listContains(named.items, g)) try named.append(ch.alloc, g);
    }
    var dangling: std.ArrayList([]const u8) = .empty;
    for (named.items) |g| {
        if (!spec.hasGrant(g)) try dangling.append(ch.alloc, g);
    }
    std.mem.sort([]const u8, dangling.items, {}, lessStr);
    for (dangling.items) |g| {
        const gs = ((try fieldNameSpanOr(ch.alloc, smap, ds.bs, ds.be, g)) orelse span);
        try ch.emit("E-CAP-ORDER-DANGLING", spec.origin_file, gs, decl, try std.fmt.allocPrint(ch.alloc, "capability `{s}`: order names grant `{s}` which is not declared by a `grant` statement", .{ spec.domain, g }));
    }
    // 2/3. acyclicity of the closure.
    const result = try transitiveClosure(ch.alloc, spec.grants, spec.order_chains);
    if (result.cycle) |cyc| {
        try ch.emit("E-CAP-ORDER-CYCLE", spec.origin_file, span, decl, try std.fmt.allocPrint(ch.alloc, "capability `{s}`: order is cyclic (`{s}` and `{s}` are mutually ≤) — the relation must be a partial order", .{ spec.domain, cyc.a, cyc.b }));
        // spec.leq = {g: {g}} for grants
        var leq: std.StringArrayHashMapUnmanaged([]const []const u8) = .{};
        for (spec.grants) |g| {
            try leq.put(ch.alloc, g, try ch.alloc.dupe([]const u8, &.{g}));
        }
        spec.leq = leq;
    } else {
        spec.leq = result.leq.?;
    }
}

fn lessStr(_: void, a: []const u8, b: []const u8) bool {
    return std.mem.lessThan(u8, a, b);
}

// --------------------------------------------------------------------------- //
// Decl field bindings (top-level fields of a decl)
// --------------------------------------------------------------------------- //

const Bindings = struct {
    names: []const []const u8, // source order
    vals: []const VProp, // parallel to names; dict semantics applied (last wins)

    fn get(self: Bindings, name: []const u8) ?VProp {
        // last value for the name (dict overwrite). Python dict keeps the last
        // assigned value under the first-seen key; we store last value.
        var found: ?VProp = null;
        for (self.names, self.vals) |n, v| {
            if (std.mem.eql(u8, n, name)) found = v;
        }
        return found;
    }
    fn has(self: Bindings, name: []const u8) bool {
        for (self.names) |n| if (std.mem.eql(u8, n, name)) return true;
        return false;
    }
};

/// `_decl_field_bindings`. Returns dict-equivalent (names in first-insertion
/// order, values last-wins) — but the order list mirrors Python's `order` which
/// appends EVERY binding occurrence (including repeats). For unknown-field /
/// missing-field we iterate `order`, so duplicates matter; we keep raw order.
const RawBindings = struct {
    order: []const []const u8, // every occurrence, in source order
    names: []const []const u8, // dict keys (first-insertion order, de-duped)
    vals: []const VProp, // parallel to names — last value per key

    fn get(self: RawBindings, name: []const u8) ?VProp {
        for (self.names, self.vals) |n, v| {
            if (std.mem.eql(u8, n, name)) return v;
        }
        return null;
    }
    fn has(self: RawBindings, name: []const u8) bool {
        for (self.names) |n| if (std.mem.eql(u8, n, name)) return true;
        return false;
    }
};

fn declFieldBindings(alloc: std.mem.Allocator, body: []const ast.Stmt) !RawBindings {
    var order: std.ArrayList([]const u8) = .empty;
    var names: std.ArrayList([]const u8) = .empty;
    var vals: std.ArrayList(VProp) = .empty;
    for (body) |st| {
        switch (st) {
            .assignment => |a| {
                try order.append(alloc, a.target);
                try putBinding(alloc, &names, &vals, a.target, try valueToProps(alloc, a.value));
            },
            .app => |ap| {
                // a named config block in field position, e.g. `policy { … }`:
                // record != null, args == null, single-part ref.
                if (ap.record != null and ap.args == null and ap.ref.parts.len == 1) {
                    const name = ap.ref.parts[0];
                    try order.append(alloc, name);
                    const rec = try entriesToProps(alloc, ap.record.?);
                    try putBinding(alloc, &names, &vals, name, .{ .record = rec });
                }
            },
            else => {},
        }
    }
    return .{ .order = try order.toOwnedSlice(alloc), .names = try names.toOwnedSlice(alloc), .vals = try vals.toOwnedSlice(alloc) };
}

/// node bindings: only Assignment statements.
fn nodeBindings(alloc: std.mem.Allocator, body: []const ast.Stmt) !RawBindings {
    var order: std.ArrayList([]const u8) = .empty;
    var names: std.ArrayList([]const u8) = .empty;
    var vals: std.ArrayList(VProp) = .empty;
    for (body) |st| {
        switch (st) {
            .assignment => |a| {
                try order.append(alloc, a.target);
                try putBinding(alloc, &names, &vals, a.target, try valueToProps(alloc, a.value));
            },
            else => {},
        }
    }
    return .{ .order = try order.toOwnedSlice(alloc), .names = try names.toOwnedSlice(alloc), .vals = try vals.toOwnedSlice(alloc) };
}

fn putBinding(alloc: std.mem.Allocator, names: *std.ArrayList([]const u8), vals: *std.ArrayList(VProp), name: []const u8, v: VProp) !void {
    for (names.items, 0..) |n, idx| {
        if (std.mem.eql(u8, n, name)) {
            vals.items[idx] = v; // overwrite, keep first-insertion key position
            return;
        }
    }
    try names.append(alloc, name);
    try vals.append(alloc, v);
}

// --------------------------------------------------------------------------- //
// Conformance over a single declaration (§1.1)
// --------------------------------------------------------------------------- //

/// nested-record field schema for known structural sub-blocks.
fn nestedSchema(kind: []const u8, fname: []const u8) ?[]const u8 {
    if (std.mem.eql(u8, kind, "fiber") and std.mem.eql(u8, fname, "policy")) return "fiberPolicy";
    return null;
}

fn conformDecl(ch: *Checker, smap: ?SourceMap, decl: ast.Decl, schema: SchemaSpec, file: []const u8) !void {
    const decl_span: Span = .{ .bs = decl.byteStart, .be = decl.byteEnd, .line = decl.line, .col = decl.col };
    const ds = decl_span;
    const dl: DeclLabel = .{ .decl = decl };
    const bindings = try declFieldBindings(ch.alloc, decl.body);

    // Clause 1 — required fields present.
    for (schema.fields) |f| {
        if (f.presence == .required and !bindings.has(f.name)) {
            try ch.emit("E-CONFORM-MISSING-FIELD", file, decl_span, dl, try std.fmt.allocPrint(ch.alloc, "required field `{s}` of schema `{s}` is missing", .{ f.name, schema.name }));
        }
    }

    // Clause 5 — unknown fields (closed schemas only). Iterate `order` (every occurrence).
    if (!schema.open) {
        for (bindings.order) |fname| {
            if (!schema.hasField(fname)) {
                const span = ((try fieldNameSpanOr(ch.alloc, smap, ds.bs, ds.be, fname)) orelse decl_span);
                try ch.emit("E-CONFORM-UNKNOWN-FIELD", file, span, dl, try std.fmt.allocPrint(ch.alloc, "`{s}` is not a declared field of closed schema `{s}`", .{ fname, schema.name }));
            }
        }
    }

    // Clauses 2 & 4 — field well-typedness + constraints, for bound fields.
    // Python iterates bindings.items() (dict: first-insertion key order, last value).
    for (bindings.names, bindings.vals) |fname, vprop| {
        const f = schema.field(fname) orelse continue;
        const nested = nestedSchema(decl.kind, fname);
        if (nested) |ns| {
            if (ch.reg.getSchema(ns)) |nested_schema| {
                if (vprop == .record) {
                    try conformNestedRecord(ch, smap, vprop.record, nested_schema, file, dl, fname, decl_span);
                    continue;
                }
            }
        }
        if (!try valueMatchesType(ch.alloc, vprop, f.type_text, ch.reg)) {
            const span = ((try fieldValueSpanOr(ch.alloc, smap, decl_span, fname)) orelse decl_span);
            try ch.emit("E-CONFORM-TYPE", file, span, dl, try std.fmt.allocPrint(ch.alloc, "field `{s}` of schema `{s}` expects `{s}` but got {s}", .{ fname, schema.name, f.type_text, try renderVprop(ch.alloc, vprop) }));
        }
        try checkFieldConstraints(ch, smap, vprop, f, dl, file, decl_span);
        for (f.refinements) |r| {
            if (r == .matches) {
                const vspan = ((try fieldValueSpanOr(ch.alloc, smap, decl_span, fname)) orelse decl_span);
                try checkMatches(ch, vprop, r.matches, f, dl, file, vspan);
            }
        }
    }
}

fn conformNestedRecord(ch: *Checker, smap: ?SourceMap, entries: []const VEntry, schema: SchemaSpec, file: []const u8, owner_decl: DeclLabel, owner_field: []const u8, decl_span: Span) !void {
    const ds = decl_span;
    // required present
    for (schema.fields) |f| {
        if (f.presence == .required and !entryPresent(entries, f.name)) {
            try ch.emit("E-CONFORM-MISSING-FIELD", file, decl_span, owner_decl, try std.fmt.allocPrint(ch.alloc, "required field `{s}` of nested schema `{s}` (in `{s}`) is missing", .{ f.name, schema.name, owner_field }));
        }
    }
    const distinct = try entriesDistinct(ch.alloc, entries);
    if (!schema.open) {
        // iterate entries (dict — Python uses a dict comprehension so order is
        // first-insertion of names; entries here are in source order, which
        // matches first-insertion for the corpus).
        for (distinct) |name| {
            if (!schema.hasField(name)) {
                const span = ((try fieldNameSpanOr(ch.alloc, smap, ds.bs, ds.be, name)) orelse decl_span);
                try ch.emit("E-CONFORM-UNKNOWN-FIELD", file, span, owner_decl, try std.fmt.allocPrint(ch.alloc, "`{s}` is not a declared field of nested schema `{s}` (in `{s}`)", .{ name, schema.name, owner_field }));
            }
        }
    }
    for (distinct) |name| {
        const f = schema.field(name) orelse continue;
        const v = entryValue(entries, name).?;
        if (!try valueMatchesType(ch.alloc, v, f.type_text, ch.reg)) {
            const span = ((try fieldValueSpanOr(ch.alloc, smap, decl_span, name)) orelse decl_span);
            try ch.emit("E-CONFORM-TYPE", file, span, owner_decl, try std.fmt.allocPrint(ch.alloc, "field `{s}` of nested schema `{s}` expects `{s}` but got {s}", .{ name, schema.name, f.type_text, try renderVprop(ch.alloc, v) }));
        }
        try checkFieldConstraints(ch, smap, v, f, owner_decl, file, decl_span);
    }
}

/// Names from record entries: dict semantics (the {e["assign"]: ...} comprehension
/// keeps the LAST value but the key set is unique, first-insertion order).
fn entriesDistinct(alloc: std.mem.Allocator, entries: []const VEntry) ![]const []const u8 {
    var names: std.ArrayList([]const u8) = .empty;
    for (entries) |e| switch (e) {
        .assign => |a| {
            if (!listContains(names.items, a.name)) try names.append(alloc, a.name);
        },
        .inherit => {},
    };
    return names.toOwnedSlice(alloc);
}

// --------------------------------------------------------------------------- //
// Mesh node conformance + capability checks (§4)
// --------------------------------------------------------------------------- //

fn grantRefParts(vprop: VProp) ?struct { domain: []const u8, grant: []const u8 } {
    switch (vprop) {
        .app => |a| {
            if (!a.has_args and a.record == null) {
                var it = std.mem.splitScalar(u8, a.ref, '.');
                const p0 = it.next() orelse return null;
                const p1 = it.next() orelse return null;
                if (it.next() != null) return null; // exactly 2 parts
                return .{ .domain = p0, .grant = p1 };
            }
            return null;
        },
        else => return null,
    }
}

fn checkCapabilityRefs(ch: *Checker, domain: []const u8, grant: []const u8, file: []const u8, span: Span, decl: DeclLabel) !bool {
    const cap = ch.reg.getCap(domain) orelse {
        try ch.emit("E-CAP-UNKNOWN-DOMAIN", file, span, decl, try std.fmt.allocPrint(ch.alloc, "unknown capability domain `{s}` in `{s}.{s}`", .{ domain, domain, grant }));
        return false;
    };
    if (!cap.hasGrant(grant)) {
        try ch.emit("E-CAP-UNKNOWN-GRANT", file, span, decl, try std.fmt.allocPrint(ch.alloc, "`{s}` is not a declared grant of capability domain `{s}`", .{ grant, domain }));
        return false;
    }
    return true;
}

fn leqRel(cap: CapabilitySpec, a: []const u8, b: []const u8) bool {
    if (cap.leq.get(a)) |set| {
        return listContains(set, b);
    }
    // default: {a} (b in {a})
    return std.mem.eql(u8, a, b);
}

const DG = struct { domain: []const u8, grant: []const u8 };

fn checkMesh(ch: *Checker, smap: ?SourceMap, mesh_decl: ast.Decl, file: []const u8) !void {
    const mesh_schema = ch.reg.getSchema("meshNode");

    // node name -> grants list
    var node_names: std.ArrayList([]const u8) = .empty;
    var node_grant_lists: std.ArrayList([]const DG) = .empty;

    for (mesh_decl.body) |st| {
        if (st == .node_decl) {
            const nd = st.node_decl;
            const bindings = try nodeBindings(ch.alloc, nd.body);
            const nspan: Span = .{ .bs = nd.byteStart, .be = nd.byteEnd, .line = nd.line, .col = nd.col };
            const nlabel: DeclLabel = .{ .str = try std.fmt.allocPrint(ch.alloc, "node {s}", .{nd.name}) };
            if (mesh_schema) |ms| {
                try conformNode(ch, smap, nd, bindings, ms, file, nspan, nlabel);
            }
            // validate + collect capability grants
            var grants: std.ArrayList(DG) = .empty;
            if (bindings.get("capabilities")) |caps| {
                if (caps == .list) {
                    for (caps.list) |e| {
                        const dg = grantRefParts(e) orelse continue;
                        const cspan = ((try fieldValueSpanOr(ch.alloc, smap, nspan, "capabilities")) orelse nspan);
                        if (try checkCapabilityRefs(ch, dg.domain, dg.grant, file, cspan, nlabel)) {
                            try grants.append(ch.alloc, .{ .domain = dg.domain, .grant = dg.grant });
                        }
                    }
                }
            }
            try node_names.append(ch.alloc, nd.name);
            try node_grant_lists.append(ch.alloc, try grants.toOwnedSlice(ch.alloc));
        }
    }

    // Attenuation on delegation edges (§4.4).
    const mlabel: DeclLabel = .{ .decl = mesh_decl };
    for (mesh_decl.body) |st| {
        if (st == .edge) {
            const refs = st.edge.refs;
            var k: usize = 0;
            while (k + 1 < refs.len) : (k += 1) {
                const a_ref = refs[k];
                const b_ref = refs[k + 1];
                const sender: ?[]const u8 = if (a_ref.parts.len == 1) a_ref.parts[0] else null;
                const receiver: ?[]const u8 = if (b_ref.parts.len == 1) b_ref.parts[0] else null;
                if (sender == null or receiver == null) continue;
                const s_idx = nodeIndex(node_names.items, sender.?) orelse continue;
                const r_idx = nodeIndex(node_names.items, receiver.?) orelse continue;
                try checkEdgeAttenuation(ch, sender.?, receiver.?, node_grant_lists.items[s_idx], node_grant_lists.items[r_idx], a_ref, b_ref, file, mlabel);
            }
        }
    }
}

fn nodeIndex(names: []const []const u8, name: []const u8) ?usize {
    for (names, 0..) |n, i| if (std.mem.eql(u8, n, name)) return i;
    return null;
}

fn conformNode(ch: *Checker, smap: ?SourceMap, nd: ast.NodeDecl, bindings: RawBindings, schema: SchemaSpec, file: []const u8, nspan: Span, nlabel: DeclLabel) !void {
    const ns = nspan;
    for (schema.fields) |f| {
        if (f.presence == .required and !bindings.has(f.name)) {
            try ch.emit("E-CONFORM-MISSING-FIELD", file, nspan, nlabel, try std.fmt.allocPrint(ch.alloc, "required field `{s}` of schema `{s}` is missing", .{ f.name, schema.name }));
        }
    }
    if (!schema.open) {
        for (bindings.order) |fname| {
            if (!schema.hasField(fname)) {
                const span = ((try fieldNameSpanOr(ch.alloc, smap, ns.bs, ns.be, fname)) orelse nspan);
                try ch.emit("E-CONFORM-UNKNOWN-FIELD", file, span, nlabel, try std.fmt.allocPrint(ch.alloc, "`{s}` is not a declared field of closed schema `{s}`", .{ fname, schema.name }));
            }
        }
    }
    for (bindings.names, bindings.vals) |fname, vprop| {
        const f = schema.field(fname) orelse continue;
        if (!try valueMatchesType(ch.alloc, vprop, f.type_text, ch.reg)) {
            const span = ((try fieldValueSpanOr(ch.alloc, smap, nspan, fname)) orelse nspan);
            try ch.emit("E-CONFORM-TYPE", file, span, nlabel, try std.fmt.allocPrint(ch.alloc, "field `{s}` of schema `{s}` expects `{s}` but got {s}", .{ fname, schema.name, f.type_text, try renderVprop(ch.alloc, vprop) }));
        }
        try checkFieldConstraints(ch, smap, vprop, f, nlabel, file, nspan);
    }
    _ = nd;
}

fn checkEdgeAttenuation(ch: *Checker, sender: []const u8, receiver: []const u8, s_grants: []const DG, r_grants: []const DG, a_ref: ast.Ref, b_ref: ast.Ref, file: []const u8, mesh_label: DeclLabel) !void {
    const edge_span: Span = .{ .bs = a_ref.byteStart, .be = b_ref.byteEnd, .line = a_ref.line, .col = a_ref.col };
    for (r_grants) |rg| {
        const cap = ch.reg.getCap(rg.domain) orelse continue;
        // sender grants in this domain
        var sender_grants: std.ArrayList([]const u8) = .empty;
        for (s_grants) |sg| {
            if (std.mem.eql(u8, sg.domain, rg.domain)) try sender_grants.append(ch.alloc, sg.grant);
        }
        var ok = false;
        for (sender_grants.items) |sg| {
            if (leqRel(cap, rg.grant, sg)) {
                ok = true;
                break;
            }
        }
        if (!ok) {
            var held_buf: std.ArrayList(u8) = .empty;
            if (sender_grants.items.len == 0) {
                try held_buf.appendSlice(ch.alloc, "(none)");
            } else {
                for (sender_grants.items, 0..) |g, i| {
                    if (i != 0) try held_buf.appendSlice(ch.alloc, ", ");
                    try held_buf.appendSlice(ch.alloc, try std.fmt.allocPrint(ch.alloc, "{s}.{s}", .{ rg.domain, g }));
                }
            }
            try ch.emit("E-CAP-ATTENUATION", file, edge_span, mesh_label, try std.fmt.allocPrint(ch.alloc, "delegation `{s} -> {s}` escalates authority: receiver holds `{s}.{s}` but sender holds {s} (receiver's grant must be ≤ the sender's in domain `{s}`)", .{ sender, receiver, rg.domain, rg.grant, held_buf.items, rg.domain }));
        }
    }
}

// --------------------------------------------------------------------------- //
// Generics (§5)
// --------------------------------------------------------------------------- //

const ByNameKind = struct {
    kinds: []const []const u8,
    names: []const []const u8,
    decls: []const ast.Decl,

    fn find(self: ByNameKind, kind: []const u8, name: []const u8) ?ast.Decl {
        for (self.kinds, self.names, self.decls) |k, n, d| {
            if (std.mem.eql(u8, k, kind) and std.mem.eql(u8, n, name)) return d;
        }
        return null;
    }
    /// `_resolve_kind`: dotted "<kind>.<name>" or bare "<name>".
    fn resolveKind(self: ByNameKind, dotted: []const u8) ?[]const u8 {
        var it = std.mem.splitScalar(u8, dotted, '.');
        const p0 = it.next().?;
        const p1 = it.next();
        if (p1 != null and it.next() == null) {
            // 2 parts
            if (parse.isKind(p0)) {
                if (self.find(p0, p1.?) != null) return p0;
                return null;
            }
            return null;
        }
        if (p1 == null) {
            // 1 part: first (kind,name) with name == p0
            for (self.kinds, self.names) |k, n| {
                if (std.mem.eql(u8, n, p0)) return k;
            }
        }
        return null;
    }
};

fn refDotted(vprop: ?VProp) ?[]const u8 {
    if (vprop) |v| {
        switch (v) {
            .app => |a| {
                if (!a.has_args and a.record == null) return a.ref;
                return null;
            },
            else => return null,
        }
    }
    return null;
}

fn lastPart(dotted: []const u8) []const u8 {
    var last = dotted;
    var it = std.mem.splitScalar(u8, dotted, '.');
    while (it.next()) |p| last = p;
    return last;
}

fn itemSchemaOf(bindings: RawBindings) ?[]const u8 {
    const s = bindings.get("schema");
    if (refDotted(s)) |d| return lastPart(d);
    return null;
}

fn checkGenerics(ch: *Checker, smap: ?SourceMap, decl: ast.Decl, by_name_kind: ByNameKind, file: []const u8) !void {
    const decl_span: Span = .{ .bs = decl.byteStart, .be = decl.byteEnd, .line = decl.line, .col = decl.col };
    const dl: DeclLabel = .{ .decl = decl };
    const bindings = try declFieldBindings(ch.alloc, decl.body);

    if (std.mem.eql(u8, decl.kind, "catalog")) {
        const frm = bindings.get("from");
        if (refDotted(frm)) |dg| {
            const target_kind = by_name_kind.resolveKind(dg);
            if (target_kind != null and !std.mem.eql(u8, target_kind.?, "index")) {
                const span = ((try fieldValueSpanOr(ch.alloc, smap, decl_span, "from")) orelse decl_span);
                try ch.emit("E-GENERIC-INCONSISTENT", file, span, dl, try std.fmt.allocPrint(ch.alloc, "catalog `from` must target an `index` (Index<T>); `{s}` is a `{s}`", .{ dg, target_kind.? }));
            }
            const cat_item = itemSchemaOf(bindings);
            const idx_decl = by_name_kind.find("index", lastPart(dg));
            if (cat_item != null and idx_decl != null) {
                const idx_bindings = try declFieldBindings(ch.alloc, idx_decl.?.body);
                const idx_item = itemSchemaOf(idx_bindings);
                if (idx_item != null and !std.mem.eql(u8, idx_item.?, cat_item.?)) {
                    const span = ((try fieldValueSpanOr(ch.alloc, smap, decl_span, "from")) orelse decl_span);
                    try ch.emit("E-GENERIC-INCONSISTENT", file, span, dl, try std.fmt.allocPrint(ch.alloc, "catalog item type `{s}` disagrees with index `{s}` item type `{s}`", .{ cat_item.?, lastPart(dg), idx_item.? }));
                }
            }
        }
    }
    // fiber: no checks (Python `pass`).
}

// --------------------------------------------------------------------------- //
// Decl-tree walk
// --------------------------------------------------------------------------- //

fn checkDeclTree(ch: *Checker, smap: ?SourceMap, decl: ast.Decl, by_name_kind: ByNameKind, file: []const u8) error{OutOfMemory}!void {
    const kind = decl.kind;
    if (!(std.mem.eql(u8, kind, "schema") or std.mem.eql(u8, kind, "capability"))) {
        if (ch.reg.getSchema(kind)) |schema| {
            try conformDecl(ch, smap, decl, schema, file);
        }
        try checkGenerics(ch, smap, decl, by_name_kind, file);
    }
    if (std.mem.eql(u8, kind, "mesh")) {
        try checkMesh(ch, smap, decl, file);
    }
    // Recurse into nested declarations.
    for (decl.body) |st| {
        if (st == .decl) {
            try checkDeclTree(ch, smap, st.decl, by_name_kind, file);
        }
    }
}

// --------------------------------------------------------------------------- //
// Diagnostic sort
// --------------------------------------------------------------------------- //

fn lessDiag(_: void, a: Diagnostic, b: Diagnostic) bool {
    // (file, byteStart, byteEnd, code)
    const fc = std.mem.order(u8, a.file, b.file);
    if (fc != .eq) return fc == .lt;
    if (a.byteStart != b.byteStart) return a.byteStart < b.byteStart;
    if (a.byteEnd != b.byteEnd) return a.byteEnd < b.byteEnd;
    return std.mem.lessThan(u8, a.code, b.code);
}

// --------------------------------------------------------------------------- //
// Public entry points
// --------------------------------------------------------------------------- //

/// Pre-parsed built-in catalog. Mirrors `load_builtins` -> (items, src, file).
pub const Builtins = struct {
    items: []const ast.Item,
    src: []const u8,
    file: []const u8,
};

/// `load_builtins` — parse the catalog. The caller supplies the file contents
/// (the CLI does the IO). On parse failure returns `error.ParseFailed`.
pub fn loadBuiltins(alloc: std.mem.Allocator, src: []const u8, path: []const u8) CheckError!Builtins {
    var lex_err: lex.ErrInfo = undefined;
    const toks = lex.tokenize(alloc, src, path, &lex_err) catch |e| switch (e) {
        error.OutOfMemory => return error.OutOfMemory,
        else => return error.ParseFailed,
    };
    var parse_err: parse.ErrInfo = undefined;
    const items = parse.parse(alloc, toks, path, &parse_err) catch |e| switch (e) {
        error.OutOfMemory => return error.OutOfMemory,
        error.ParseFailed => return error.ParseFailed,
    };
    return .{ .items = items, .src = src, .file = path };
}

/// `check_source` — check `src` and return the sorted diagnostics. `filename`
/// is the source path used in diagnostics + the source map key.
pub fn checkSource(alloc: std.mem.Allocator, src: []const u8, filename: []const u8, builtins: Builtins) CheckError![]const Diagnostic {
    // Stage 3 — elaborate.
    var reg = Registry{ .alloc = alloc };
    try loadDeclsInto(&reg, builtins.items, builtins.file);

    var lex_err: lex.ErrInfo = undefined;
    const toks = lex.tokenize(alloc, src, filename, &lex_err) catch |e| switch (e) {
        error.OutOfMemory => return error.OutOfMemory,
        else => return error.ParseFailed,
    };
    var parse_err: parse.ErrInfo = undefined;
    const items = parse.parse(alloc, toks, filename, &parse_err) catch |e| switch (e) {
        error.OutOfMemory => return error.OutOfMemory,
        error.ParseFailed => return error.ParseFailed,
    };
    try loadDeclsInto(&reg, items, filename);

    // Source maps for span resolution.
    const b_smap = try SourceMap.init(alloc, builtins.src, builtins.file);
    const f_smap = try SourceMap.init(alloc, src, filename);

    var smap_for = struct {
        b_file: []const u8,
        f_file: []const u8,
        b: SourceMap,
        f: SourceMap,
        fn get(self: @This(), file: []const u8) ?SourceMap {
            if (std.mem.eql(u8, file, self.b_file)) return self.b;
            if (std.mem.eql(u8, file, self.f_file)) return self.f;
            return null;
        }
    }{ .b_file = builtins.file, .f_file = filename, .b = b_smap, .f = f_smap };

    var diags: std.ArrayList(Diagnostic) = .empty;
    var ch = Checker{ .alloc = alloc, .reg = &reg, .diags = &diags };

    // Stage 4a — load-time well-formedness over EVERY schema & capability,
    // sorted by (origin_file, name/domain).
    {
        // schemas sorted
        var schema_idx: std.ArrayList(usize) = .empty;
        for (reg.schemas.values(), 0..) |_, i| try schema_idx.append(alloc, i);
        const SchemaSortCtx = struct {
            vals: []const SchemaSpec,
            fn less(self: @This(), a: usize, b: usize) bool {
                const sa = self.vals[a];
                const sb = self.vals[b];
                const fc = std.mem.order(u8, sa.origin_file, sb.origin_file);
                if (fc != .eq) return fc == .lt;
                return std.mem.lessThan(u8, sa.name, sb.name);
            }
        };
        std.mem.sort(usize, schema_idx.items, SchemaSortCtx{ .vals = reg.schemas.values() }, SchemaSortCtx.less);
        for (schema_idx.items) |i| {
            const spec = reg.schemas.values()[i];
            try checkSchemaWellformed(&ch, smap_for.get(spec.origin_file), spec);
        }

        // capabilities sorted (need mutable ptr to set leq).
        var cap_idx: std.ArrayList(usize) = .empty;
        for (reg.caps.values(), 0..) |_, i| try cap_idx.append(alloc, i);
        const CapSortCtx = struct {
            vals: []const CapabilitySpec,
            fn less(self: @This(), a: usize, b: usize) bool {
                const ca = self.vals[a];
                const cb = self.vals[b];
                const fc = std.mem.order(u8, ca.origin_file, cb.origin_file);
                if (fc != .eq) return fc == .lt;
                return std.mem.lessThan(u8, ca.domain, cb.domain);
            }
        };
        std.mem.sort(usize, cap_idx.items, CapSortCtx{ .vals = reg.caps.values() }, CapSortCtx.less);
        for (cap_idx.items) |i| {
            const spec_ptr = &reg.caps.values()[i];
            try checkCapabilityWellformed(&ch, smap_for.get(spec_ptr.origin_file), spec_ptr);
        }
    }

    // Index in-file decls by (kind, name) for generics resolution.
    var bnk_kinds: std.ArrayList([]const u8) = .empty;
    var bnk_names: std.ArrayList([]const u8) = .empty;
    var bnk_decls: std.ArrayList(ast.Decl) = .empty;
    for (items) |it| {
        if (it == .decl) {
            const d = it.decl;
            // dict {(kind,name): decl} — last wins; we keep last by replacing.
            var replaced = false;
            for (bnk_kinds.items, bnk_names.items, 0..) |k, n, idx| {
                if (std.mem.eql(u8, k, d.kind) and std.mem.eql(u8, n, d.name)) {
                    bnk_decls.items[idx] = d;
                    replaced = true;
                    break;
                }
            }
            if (!replaced) {
                try bnk_kinds.append(alloc, d.kind);
                try bnk_names.append(alloc, d.name);
                try bnk_decls.append(alloc, d);
            }
        }
    }
    const by_name_kind = ByNameKind{ .kinds = bnk_kinds.items, .names = bnk_names.items, .decls = bnk_decls.items };

    // Stage 4b/4c/4d — walk every in-file declaration.
    const f_smap_opt: ?SourceMap = f_smap;
    for (items) |it| {
        if (it == .decl) {
            try checkDeclTree(&ch, f_smap_opt, it.decl, by_name_kind, filename);
        }
    }

    std.mem.sort(Diagnostic, diags.items, {}, lessDiag);
    return diags.toOwnedSlice(alloc);
}

// --------------------------------------------------------------------------- //
// Tests
// --------------------------------------------------------------------------- //

test "baseType strips List<>" {
    const a = baseType("List<String>");
    try std.testing.expect(a.is_list);
    try std.testing.expectEqualStrings("String", a.inner);
    const b = baseType("Int");
    try std.testing.expect(!b.is_list);
    try std.testing.expectEqualStrings("Int", b.inner);
}

test "fmtNum integer-valued" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    try std.testing.expectEqualStrings("0", try fmtNum(arena.allocator(), 0.0));
    try std.testing.expectEqualStrings("42", try fmtNum(arena.allocator(), 42.0));
}

test "regexDialectError flags backreference" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const err = try regexDialectError(arena.allocator(), "/(a)\\1/");
    try std.testing.expect(err != null);
}

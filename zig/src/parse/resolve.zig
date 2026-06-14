//! vakedc.resolve (Zig port) — build the LPG from a parsed AST (0011 stages 1-2).
//! Faithful port of `vakedc/resolve.py:build_graph`.
//!
//! Walks the top-level items, instantiating one `GraphNode` per declaration with
//! byte-exact provenance, maintaining a lexically-scoped symbol table, and
//! collecting refs on a worklist tagged with edge-label semantics. At end of
//! parse the worklist is resolved against the scope captured at each ref site
//! (forward refs work); a ref whose head resolves to no in-file declaration
//! produces ONE external stub per distinct dotted path.
//!
//! Node `props` are built incrementally (assignments insert/overwrite keys;
//! grants/order/inherit append to list keys), then finalized into the
//! `GraphNode.props` `Value` after the worklist runs. Object-key ordering is
//! irrelevant (the canonical writer sorts keys); list order is preserved.

const std = @import("std");
const ast = @import("ast.zig");
const core = @import("vaked-core");
const Value = core.Value;
const Graph = core.Graph;
const GraphNode = core.GraphNode;
const GraphEdge = core.GraphEdge;
const Provenance = core.Provenance;
const Span = core.Span;
const nodeId = core.nodeId;
const parser = @import("parser.zig");

pub const ResolveError = error{
    /// Mirrors Python's `to_canonical_json` crashing on a non-JSON-serializable
    /// `Literal`/`ListLit` left in a `default`/`oneof` field refinement: the
    /// graph builds but serialization fails → empty stdout, exit 1.
    Unserializable,
    OutOfMemory,
};

const DEPENDS_FIELDS = [_][]const u8{ "input", "output", "from", "source", "engine" };

fn isDependsField(s: []const u8) bool {
    for (DEPENDS_FIELDS) |f| {
        if (std.mem.eql(u8, f, s)) return true;
    }
    return false;
}

// --------------------------------------------------------------------------- //
// scope + worklist
// --------------------------------------------------------------------------- //

const Scope = struct {
    parent: ?*Scope,
    bindings: std.StringArrayHashMapUnmanaged([]const u8) = .empty,
    alloc: std.mem.Allocator,

    fn init(alloc: std.mem.Allocator, parent: ?*Scope) !*Scope {
        const s = try alloc.create(Scope);
        s.* = .{ .parent = parent, .alloc = alloc };
        return s;
    }

    fn define(self: *Scope, name: []const u8, nid: []const u8) !void {
        try self.bindings.put(self.alloc, name, nid);
    }

    fn lookup(self: *Scope, name: []const u8) ?[]const u8 {
        var s: ?*Scope = self;
        while (s) |sc| {
            if (sc.bindings.get(name)) |nid| return nid;
            s = sc.parent;
        }
        return null;
    }
};

const Label = enum { routes_to, depends_on, requires_capability, member_of };

fn labelName(l: Label) []const u8 {
    return switch (l) {
        .routes_to => "routes_to",
        .depends_on => "depends_on",
        .requires_capability => "requires_capability",
        .member_of => "member_of",
    };
}

const RefTask = struct {
    ref: ast.Ref,
    label: Label,
    source_id: []const u8,
    scope: *Scope,
    partner: ?ast.Ref = null, // for routes_to: the 'to' ref
    edge_props: Value = .{ .object = &.{} },
};

// --------------------------------------------------------------------------- //
// per-node prop builder (incremental; finalized after the worklist)
// --------------------------------------------------------------------------- //

const Slot = union(enum) {
    scalar: Value,
    list: std.ArrayList(Value),
};

const NodeProps = struct {
    // ordered map: key -> slot. Insertion order is irrelevant (writer sorts).
    map: std.StringArrayHashMapUnmanaged(Slot) = .empty,
    alloc: std.mem.Allocator,

    fn record(self: *NodeProps, key: []const u8, value: Value) !void {
        try self.map.put(self.alloc, key, .{ .scalar = value });
    }

    fn appendList(self: *NodeProps, key: []const u8, values: []const Value) !void {
        const gop = try self.map.getOrPut(self.alloc, key);
        if (!gop.found_existing) gop.value_ptr.* = .{ .list = .empty };
        switch (gop.value_ptr.*) {
            .list => |*l| {
                for (values) |v| try l.append(self.alloc, v);
            },
            .scalar => {
                // Python's setdefault would not overwrite a scalar with a list;
                // in the corpus the append keys (grants/order/inherit) are never
                // also scalar keys, so this branch is unreachable.
                var l: std.ArrayList(Value) = .empty;
                for (values) |v| try l.append(self.alloc, v);
                gop.value_ptr.* = .{ .list = l };
            },
        }
    }

    fn finalize(self: *NodeProps) !Value {
        var fields: std.ArrayList(Value.Field) = .empty;
        var it = self.map.iterator();
        while (it.next()) |entry| {
            const v: Value = switch (entry.value_ptr.*) {
                .scalar => |sv| sv,
                .list => |l| .{ .array = try self.alloc.dupe(Value, l.items) },
            };
            try fields.append(self.alloc, .{ .key = entry.key_ptr.*, .value = v });
        }
        return .{ .object = try fields.toOwnedSlice(self.alloc) };
    }
};

// --------------------------------------------------------------------------- //
// resolver
// --------------------------------------------------------------------------- //

const Resolver = struct {
    items: []const ast.Item,
    basename: []const u8,
    provfile: []const u8,
    graph: *Graph,
    worklist: std.ArrayList(RefTask) = .empty,
    // node id -> its prop builder (finalized at the end).
    node_props: std.StringArrayHashMapUnmanaged(*NodeProps) = .empty,
    unserializable: bool = false,
    alloc: std.mem.Allocator,

    fn nodePropsFor(self: *Resolver, id: []const u8) !*NodeProps {
        const gop = try self.node_props.getOrPut(self.alloc, id);
        if (!gop.found_existing) {
            const np = try self.alloc.create(NodeProps);
            np.* = .{ .alloc = self.alloc };
            gop.value_ptr.* = np;
        }
        return gop.value_ptr.*;
    }

    fn build(self: *Resolver) ResolveError!void {
        const root = try Scope.init(self.alloc, null);
        // Pre-define all top-level decl names so sibling/forward refs resolve.
        for (self.items) |it| {
            switch (it) {
                .decl => |d| try root.define(d.name, try nodeId(self.alloc, self.basename, &.{d.name})),
                else => {},
            }
        }
        for (self.items) |it| {
            switch (it) {
                .import => |imp| try self.handleImport(imp),
                .decl => |d| try self.buildDecl(d, &.{d.name}, root, null),
            }
        }
        try self.resolveWorklist();
        // Finalize props into the GraphNodes.
        var it = self.node_props.iterator();
        while (it.next()) |entry| {
            if (self.graph.getNode(entry.key_ptr.*)) |gn| {
                gn.props = try entry.value_ptr.*.finalize();
            }
        }
    }

    // --- imports --------------------------------------------------------- //

    fn handleImport(self: *Resolver, imp: ast.Import) !void {
        const file_id = try std.fmt.allocPrint(self.alloc, "{s}#", .{self.basename});
        if (!self.graph.hasNode(file_id)) {
            const labels = try self.alloc.dupe([]const u8, &.{"file"});
            _ = try self.graph.addNode(.{
                .id = file_id,
                .kind = "file",
                .name = self.basename,
                .labels = labels,
                .props = .{ .object = &.{} },
                .provenance = null,
            });
        }
        const stub = try self.graph.ensureExternal(imp.path);
        try self.graph.addEdge(.{ .from = file_id, .to = stub.id, .label = "imports", .props = .{ .object = &.{} } });
    }

    // --- declarations ---------------------------------------------------- //

    fn buildDecl(self: *Resolver, decl: ast.Decl, chain: []const []const u8, scope: *Scope, parent_id: ?[]const u8) ResolveError!void {
        const nid = try nodeId(self.alloc, self.basename, chain);
        const prov = Provenance{
            .file = self.provfile,
            .decl = try std.fmt.allocPrint(self.alloc, "{s} {s}", .{ decl.kind, decl.name }),
            .span = .{ .byteStart = decl.byteStart, .byteEnd = decl.byteEnd, .line = decl.line, .col = decl.col },
        };
        const np = try self.nodePropsFor(nid);
        if (decl.signature) |sig| {
            try np.record("signature", try self.signatureToProps(sig));
        }
        if (decl.annotations.len > 0) {
            var arr: std.ArrayList(Value) = .empty;
            for (decl.annotations) |a| try arr.append(self.alloc, try self.annotationToProps(a));
            try np.record("annotations", .{ .array = try arr.toOwnedSlice(self.alloc) });
        }
        const labels = try self.alloc.dupe([]const u8, &.{ "decl", decl.kind });
        _ = try self.graph.addNode(.{
            .id = nid,
            .kind = decl.kind,
            .name = decl.name,
            .labels = labels,
            .props = .{ .object = &.{} }, // finalized later
            .provenance = prov,
        });
        if (parent_id) |pid| {
            try self.graph.addEdge(.{ .from = pid, .to = nid, .label = "contains", .props = .{ .object = &.{} } });
        }

        // New lexical scope for the body; pre-define child decl/node names.
        const child_scope = try Scope.init(self.alloc, scope);
        for (decl.body) |st| {
            switch (st) {
                .decl => |d| try child_scope.define(d.name, try nodeId(self.alloc, self.basename, try concat(self.alloc, chain, d.name))),
                .node_decl => |nd| try child_scope.define(nd.name, try nodeId(self.alloc, self.basename, try concat(self.alloc, chain, nd.name))),
                else => {},
            }
        }
        try self.buildBody(.{ .decl = decl }, decl.body, chain, nid, child_scope);
    }

    fn buildBody(self: *Resolver, owner: Owner, stmts: []const ast.Stmt, chain: []const []const u8, owner_id: []const u8, scope: *Scope) ResolveError!void {
        for (stmts) |st| try self.buildStmt(owner, st, chain, owner_id, scope);
    }

    const Owner = union(enum) {
        decl: ast.Decl,
        node_decl: ast.NodeDecl,

        fn kind(self: Owner) ?[]const u8 {
            return switch (self) {
                .decl => |d| d.kind,
                .node_decl => null,
            };
        }
    };

    fn buildStmt(self: *Resolver, owner: Owner, st: ast.Stmt, chain: []const []const u8, owner_id: []const u8, scope: *Scope) ResolveError!void {
        switch (st) {
            .decl => |d| try self.buildDecl(d, try concat(self.alloc, chain, d.name), scope, owner_id),
            .node_decl => |nd| try self.buildNodeDecl(nd, chain, owner_id, scope),
            .edge => |e| try self.buildEdge(e, scope, owner_id),
            .assignment => |a| try self.buildAssignment(owner, a, owner_id, scope),
            .app => {}, // bare app statement: no inter-node edge
            .field_decl => |f| {
                const np = try self.nodePropsFor(owner_id);
                const key = try std.fmt.allocPrint(self.alloc, "field:{s}", .{f.name});
                try np.record(key, try self.fieldToProps(f));
            },
            .grant_decl => |g| {
                var vals: std.ArrayList(Value) = .empty;
                for (g.names) |nm| try vals.append(self.alloc, .{ .string = nm });
                try (try self.nodePropsFor(owner_id)).appendList("grants", vals.items);
            },
            .order_decl => |o| {
                var vals: std.ArrayList(Value) = .empty;
                for (o.chains) |chn| {
                    var inner: std.ArrayList(Value) = .empty;
                    for (chn) |nm| try inner.append(self.alloc, .{ .string = nm });
                    try vals.append(self.alloc, .{ .array = try inner.toOwnedSlice(self.alloc) });
                }
                try (try self.nodePropsFor(owner_id)).appendList("order", vals.items);
            },
            .open_decl => {
                try (try self.nodePropsFor(owner_id)).record("open", .{ .bool = true });
            },
            .inherit_stmt => |ih| {
                var vals: std.ArrayList(Value) = .empty;
                for (ih.names) |nm| try vals.append(self.alloc, .{ .string = nm });
                try (try self.nodePropsFor(owner_id)).appendList("inherit", vals.items);
            },
        }
    }

    fn buildNodeDecl(self: *Resolver, nd: ast.NodeDecl, chain: []const []const u8, owner_id: []const u8, scope: *Scope) ResolveError!void {
        const chain2 = try concat(self.alloc, chain, nd.name);
        const nid = try nodeId(self.alloc, self.basename, chain2);
        const prov = Provenance{
            .file = self.provfile,
            .decl = try std.fmt.allocPrint(self.alloc, "node {s}", .{nd.name}),
            .span = .{ .byteStart = nd.byteStart, .byteEnd = nd.byteEnd, .line = nd.line, .col = nd.col },
        };
        _ = try self.nodePropsFor(nid); // ensure props exist (empty object)
        const labels = try self.alloc.dupe([]const u8, &.{"node"});
        _ = try self.graph.addNode(.{
            .id = nid,
            .kind = "node",
            .name = nd.name,
            .labels = labels,
            .props = .{ .object = &.{} },
            .provenance = prov,
        });
        try self.graph.addEdge(.{ .from = owner_id, .to = nid, .label = "contains", .props = .{ .object = &.{} } });
        const child_scope = try Scope.init(self.alloc, scope);
        for (nd.body) |st| {
            switch (st) {
                .decl => |d| try child_scope.define(d.name, try nodeId(self.alloc, self.basename, try concat(self.alloc, chain2, d.name))),
                .node_decl => |n2| try child_scope.define(n2.name, try nodeId(self.alloc, self.basename, try concat(self.alloc, chain2, n2.name))),
                else => {},
            }
        }
        try self.buildBody(.{ .node_decl = nd }, nd.body, chain2, nid, child_scope);
    }

    fn buildEdge(self: *Resolver, edge: ast.Edge, scope: *Scope, owner_id: []const u8) !void {
        // `a -> b -> c [: "label"]` : routes_to edges along consecutive pairs.
        var edge_props: Value = .{ .object = &.{} };
        if (edge.label) |lbl| {
            const fields = try self.alloc.dupe(Value.Field, &.{.{ .key = "label", .value = .{ .string = lbl } }});
            edge_props = .{ .object = fields };
        }
        var k: usize = 0;
        while (k + 1 < edge.refs.len) : (k += 1) {
            try self.worklist.append(self.alloc, .{
                .ref = edge.refs[k],
                .label = .routes_to,
                .source_id = owner_id,
                .scope = scope,
                .partner = edge.refs[k + 1],
                .edge_props = edge_props,
            });
        }
    }

    // --- assignments ----------------------------------------------------- //

    fn buildAssignment(self: *Resolver, owner: Owner, asn: ast.Assignment, owner_id: []const u8, scope: *Scope) !void {
        const target = asn.target;
        if (isDependsField(target)) {
            try self.deferValueRefs(asn.value, .depends_on, owner_id, scope);
        } else if (std.mem.eql(u8, target, "fibers") and ownerKindEql(owner, "parallel")) {
            try self.deferValueRefs(asn.value, .member_of, owner_id, scope);
        } else if (std.mem.eql(u8, target, "capabilities")) {
            try self.deferValueRefs(asn.value, .requires_capability, owner_id, scope);
        }
        var prop_val = try self.valueToProps(asn.value);
        if (!std.mem.eql(u8, asn.op, "=")) {
            const fields = try self.alloc.dupe(Value.Field, &.{
                .{ .key = "op", .value = .{ .string = asn.op } },
                .{ .key = "value", .value = prop_val },
            });
            prop_val = .{ .object = fields };
        }
        try (try self.nodePropsFor(owner_id)).record(target, prop_val);
    }

    fn deferValueRefs(self: *Resolver, val: ast.Expr, label: Label, owner_id: []const u8, scope: *Scope) !void {
        const refs = try refsInValue(self.alloc, val);
        for (refs) |r| {
            try self.worklist.append(self.alloc, .{ .ref = r, .label = label, .source_id = owner_id, .scope = scope });
        }
    }

    // --- worklist resolution --------------------------------------------- //

    fn resolveWorklist(self: *Resolver) !void {
        for (self.worklist.items) |task| {
            if (task.label == .routes_to) {
                const src = try self.resolveRef(task.ref, task.scope);
                const dst = try self.resolveRef(task.partner.?, task.scope);
                try self.graph.addEdge(.{ .from = src, .to = dst, .label = "routes_to", .props = task.edge_props });
            } else {
                const tgt = try self.resolveRef(task.ref, task.scope);
                try self.graph.addEdge(.{ .from = task.source_id, .to = tgt, .label = labelName(task.label), .props = .{ .object = &.{} } });
            }
        }
    }

    fn resolveRef(self: *Resolver, ref: ast.Ref, scope: *Scope) ![]const u8 {
        const head = ref.head();
        // bare in-file name -> its decl node
        if (ref.parts.len == 1) {
            if (scope.lookup(head)) |head_id| return head_id;
            return (try self.graph.ensureExternal(try ref.dotted(self.alloc))).id;
        }
        // <kind>.<name> addressing of an in-file decl of that kind
        if (ref.parts.len == 2 and parser.isKind(head)) {
            if (scope.lookup(ref.parts[1])) |target_id| {
                if (self.graph.getNode(target_id)) |node| {
                    if (std.mem.eql(u8, node.kind, head)) return target_id;
                }
            }
        }
        // head in-file but a dotted member: only if the exact nested id exists
        if (scope.lookup(head) != null) {
            const candidate = try nodeId(self.alloc, self.basename, ref.parts);
            if (self.graph.hasNode(candidate)) return candidate;
        }
        return (try self.graph.ensureExternal(try ref.dotted(self.alloc))).id;
    }

    // --- value -> props -------------------------------------------------- //

    fn valueToProps(self: *Resolver, v: ast.Expr) ResolveError!Value {
        switch (v) {
            .literal => |lit| {
                const fields = try self.alloc.dupe(Value.Field, &.{
                    .{ .key = "lit", .value = .{ .string = lit.kind.lower() } },
                    .{ .key = "value", .value = .{ .string = lit.value } },
                });
                return .{ .object = fields };
            },
            .list => |ll| {
                var arr: std.ArrayList(Value) = .empty;
                for (ll.items) |x| try arr.append(self.alloc, try self.valueToProps(x));
                return .{ .array = try arr.toOwnedSlice(self.alloc) };
            },
            .record => |rl| {
                const entries = try self.entriesToProps(rl.entries);
                const fields = try self.alloc.dupe(Value.Field, &.{
                    .{ .key = "record", .value = entries },
                });
                return .{ .object = fields };
            },
            .app => |a| {
                var fields: std.ArrayList(Value.Field) = .empty;
                try fields.append(self.alloc, .{ .key = "ref", .value = .{ .string = try a.ref.dotted(self.alloc) } });
                if (a.args) |args| {
                    var arr: std.ArrayList(Value) = .empty;
                    for (args) |x| try arr.append(self.alloc, try self.valueToProps(x));
                    try fields.append(self.alloc, .{ .key = "args", .value = .{ .array = try arr.toOwnedSlice(self.alloc) } });
                }
                if (a.record) |rec| {
                    try fields.append(self.alloc, .{ .key = "record", .value = try self.entriesToProps(rec) });
                }
                return .{ .object = try fields.toOwnedSlice(self.alloc) };
            },
        }
    }

    fn entriesToProps(self: *Resolver, entries: []const ast.Entry) ResolveError!Value {
        var arr: std.ArrayList(Value) = .empty;
        for (entries) |e| try arr.append(self.alloc, try self.entryToProps(e));
        return .{ .array = try arr.toOwnedSlice(self.alloc) };
    }

    fn entryToProps(self: *Resolver, e: ast.Entry) ResolveError!Value {
        switch (e) {
            .assignment => |a| {
                const fields = try self.alloc.dupe(Value.Field, &.{
                    .{ .key = "assign", .value = .{ .string = a.target } },
                    .{ .key = "op", .value = .{ .string = a.op } },
                    .{ .key = "value", .value = try self.valueToProps(a.value) },
                });
                return .{ .object = fields };
            },
            .inherit => |ih| {
                var arr: std.ArrayList(Value) = .empty;
                for (ih.names) |nm| try arr.append(self.alloc, .{ .string = nm });
                const fields = try self.alloc.dupe(Value.Field, &.{
                    .{ .key = "inherit", .value = .{ .array = try arr.toOwnedSlice(self.alloc) } },
                });
                return .{ .object = fields };
            },
        }
    }

    fn fieldToProps(self: *Resolver, f: ast.FieldDecl) ResolveError!Value {
        // refinements = [list(r) for r in f.refinements].  Each refinement tuple
        // becomes an array. For `default`/`oneof` Python leaves a raw Literal/
        // ListLit AST node in the array, which `json.dumps` cannot serialize →
        // the whole `parse --print` crashes (empty stdout, exit 1). We reproduce
        // that observable behavior by flagging the graph unserializable.
        var refs: std.ArrayList(Value) = .empty;
        for (f.refinements) |r| {
            const item: Value = switch (r) {
                .word => |w| blk: {
                    const a = try self.alloc.dupe(Value, &.{.{ .string = w }});
                    break :blk .{ .array = a };
                },
                .matches => |m| blk: {
                    const a = try self.alloc.dupe(Value, &.{ .{ .string = "matches" }, .{ .string = m } });
                    break :blk .{ .array = a };
                },
                .cmp => |c| blk: {
                    const a = try self.alloc.dupe(Value, &.{ .{ .string = "cmp" }, .{ .string = c.op }, .{ .string = c.num } });
                    break :blk .{ .array = a };
                },
                .range => |rg| blk: {
                    const a = try self.alloc.dupe(Value, &.{ .{ .string = "range" }, .{ .string = rg.lo }, .{ .string = rg.hi } });
                    break :blk .{ .array = a };
                },
                .default, .oneof => {
                    self.unserializable = true;
                    return error.Unserializable;
                },
            };
            try refs.append(self.alloc, item);
        }
        const fields = try self.alloc.dupe(Value.Field, &.{
            .{ .key = "type", .value = .{ .string = f.type.text } },
            .{ .key = "refinements", .value = .{ .array = try refs.toOwnedSlice(self.alloc) } },
        });
        return .{ .object = fields };
    }

    fn signatureToProps(self: *Resolver, sig: ast.Signature) ResolveError!Value {
        var params: std.ArrayList(Value) = .empty;
        for (sig.params) |p| {
            const default_val: Value = if (p.default) |d| try self.valueToProps(d) else .null;
            const pf = try self.alloc.dupe(Value.Field, &.{
                .{ .key = "name", .value = .{ .string = p.name } },
                .{ .key = "type", .value = .{ .string = p.type.text } },
                .{ .key = "default", .value = default_val },
            });
            try params.append(self.alloc, .{ .object = pf });
        }
        const ret_val: Value = if (sig.ret) |r| .{ .string = r.text } else .null;
        const fields = try self.alloc.dupe(Value.Field, &.{
            .{ .key = "params", .value = .{ .array = try params.toOwnedSlice(self.alloc) } },
            .{ .key = "return", .value = ret_val },
        });
        return .{ .object = fields };
    }

    fn annotationToProps(self: *Resolver, a: ast.Annotation) ResolveError!Value {
        const args_val: Value = if (a.args) |args| blk: {
            var arr: std.ArrayList(Value) = .empty;
            for (args) |x| try arr.append(self.alloc, try self.valueToProps(x));
            break :blk .{ .array = try arr.toOwnedSlice(self.alloc) };
        } else .null;
        const fields = try self.alloc.dupe(Value.Field, &.{
            .{ .key = "name", .value = .{ .string = a.name } },
            .{ .key = "args", .value = args_val },
        });
        return .{ .object = fields };
    }
};

fn ownerKindEql(owner: Resolver.Owner, k: []const u8) bool {
    if (owner.kind()) |ok| return std.mem.eql(u8, ok, k);
    return false;
}

// --------------------------------------------------------------------------- //
// free helpers
// --------------------------------------------------------------------------- //

/// `_is_bare_ref`: an App with no parens and no record block.
fn isBareRef(x: ast.Expr) bool {
    return switch (x) {
        .app => |a| a.args == null and a.record == null,
        else => false,
    };
}

/// `_refs_in_value`: the bare-ref dependency targets in a value.
fn refsInValue(alloc: std.mem.Allocator, v: ast.Expr) ![]const ast.Ref {
    var out: std.ArrayList(ast.Ref) = .empty;
    switch (v) {
        .app => |a| {
            if (a.args == null and a.record == null) try out.append(alloc, a.ref);
        },
        .list => |ll| {
            for (ll.items) |x| {
                if (isBareRef(x)) try out.append(alloc, x.app.ref);
            }
        },
        else => {},
    }
    return out.toOwnedSlice(alloc);
}

/// chain ++ [name] in the arena.
fn concat(alloc: std.mem.Allocator, chain: []const []const u8, name: []const u8) ![]const []const u8 {
    const out = try alloc.alloc([]const u8, chain.len + 1);
    @memcpy(out[0..chain.len], chain);
    out[chain.len] = name;
    return out;
}

/// Build the LPG from parsed items. `unserializable_out` (if non-null) is set
/// true when the graph cannot be serialized (Python would crash in json.dumps),
/// which the CLI maps to exit 1 + empty stdout.
pub fn buildGraph(alloc: std.mem.Allocator, graph: *Graph, items: []const ast.Item, filename: []const u8, unserializable_out: ?*bool) ResolveError!void {
    var r = Resolver{
        .items = items,
        .basename = std.fs.path.basename(filename),
        .provfile = filename,
        .graph = graph,
        .alloc = alloc,
    };
    r.build() catch |e| {
        if (e == error.Unserializable) {
            if (unserializable_out) |p| p.* = true;
        }
        return e;
    };
}

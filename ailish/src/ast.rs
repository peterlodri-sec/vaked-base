//! Typed AST for AI-lish V1 (RFC §2 grammar, §3 register monads).
//!
//! A `Message` is a sequence of `Frame`s. Each frame is tagged with a
//! [`Register`] and carries an ordered list of [`Line`]s. The AST is the
//! contract between the parser (which produces it from V1 text) and both the
//! guardrail (which validates §3) and the formatter (which renders it back).

/// The eight V1 registers (RFC §2 `register`, compact forms in §5).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Register {
    Think,
    Plan,
    Tool,
    Risk,
    Artifact,
    Commit,
    Review,
    Bench,
}

impl Register {
    /// Canonical long form, e.g. `R:think`.
    pub fn long(self) -> &'static str {
        match self {
            Register::Think => "R:think",
            Register::Plan => "R:plan",
            Register::Tool => "R:tool",
            Register::Risk => "R:risk",
            Register::Artifact => "R:artifact",
            Register::Commit => "R:commit",
            Register::Review => "R:review",
            Register::Bench => "R:bench",
        }
    }

    /// Compact form (RFC §5), e.g. `!T`.
    pub fn compact(self) -> &'static str {
        match self {
            Register::Think => "!T",
            Register::Plan => "!P",
            Register::Tool => "!X",
            Register::Risk => "!R",
            Register::Artifact => "!A",
            Register::Commit => "!C",
            Register::Review => "!V",
            Register::Bench => "!B",
        }
    }

    /// Parse either the long (`R:think`) or compact (`!T`) header token.
    pub fn from_token(s: &str) -> Option<Register> {
        match s {
            "R:think" | "!T" => Some(Register::Think),
            "R:plan" | "!P" => Some(Register::Plan),
            "R:tool" | "!X" => Some(Register::Tool),
            "R:risk" | "!R" => Some(Register::Risk),
            "R:artifact" | "!A" => Some(Register::Artifact),
            "R:commit" | "!C" => Some(Register::Commit),
            "R:review" | "!V" => Some(Register::Review),
            "R:bench" | "!B" => Some(Register::Bench),
            _ => None,
        }
    }
}

/// An SSA register reference, `%N` (RFC §2 `variable`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct Var(pub u64);

/// A typed atom (RFC §2 `typed_atom`). Numbers keep their source lexeme so the
/// formatter is byte-faithful (and therefore idempotent).
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Atom {
    /// `number` — stored as the original lexeme (e.g. `61`, `-1.5`).
    Number(String),
    /// `quoted` — the content without the surrounding `"`.
    Quoted(String),
    /// `bool` — `true` / `false`.
    Bool(bool),
    /// `env` — a `$ident` environment / secret reference (ident without `$`).
    Env(String),
    /// `path` — a bareword path token.
    Path(String),
    /// `symbol` — a `` `…` `` token (content without the backticks).
    Symbol(String),
}

/// An operand: a variable or an atom (RFC §2 `operand`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Operand {
    Var(Var),
    Atom(Atom),
}

/// Side-effecting and pure verbs (RFC §2 `verb`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Verb {
    Fetch,
    Read,
    Edit,
    Write,
    Test,
    Build,
    Diff,
    Commit,
    Open,
    Merge,
    LaunchAgent,
    AgentWrite,
    CheckPermission,
    Block,
}

impl Verb {
    pub fn name(self) -> &'static str {
        match self {
            Verb::Fetch => "fetch",
            Verb::Read => "read",
            Verb::Edit => "edit",
            Verb::Write => "write",
            Verb::Test => "test",
            Verb::Build => "build",
            Verb::Diff => "diff",
            Verb::Commit => "commit",
            Verb::Open => "open",
            Verb::Merge => "merge",
            Verb::LaunchAgent => "launch_agent",
            Verb::AgentWrite => "agent_write",
            Verb::CheckPermission => "check_permission",
            Verb::Block => "block",
        }
    }

    pub fn from_name(s: &str) -> Option<Verb> {
        Some(match s {
            "fetch" => Verb::Fetch,
            "read" => Verb::Read,
            "edit" => Verb::Edit,
            "write" => Verb::Write,
            "test" => Verb::Test,
            "build" => Verb::Build,
            "diff" => Verb::Diff,
            "commit" => Verb::Commit,
            "open" => Verb::Open,
            "merge" => Verb::Merge,
            "launch_agent" => Verb::LaunchAgent,
            "agent_write" => Verb::AgentWrite,
            "check_permission" => Verb::CheckPermission,
            "block" => Verb::Block,
            _ => return None,
        })
    }

    /// Verbs that mutate state directly. Used by the guardrail (§3) to forbid
    /// side effects in `R:think` / `R:review` and bare side effects in
    /// `R:plan`. `launch_agent` is treated as orchestration, not a direct
    /// mutation, matching the RFC §4 example where `R:plan` may launch agents.
    pub fn is_side_effecting(self) -> bool {
        matches!(
            self,
            Verb::Edit
                | Verb::Write
                | Verb::Commit
                | Verb::Open
                | Verb::Merge
                | Verb::AgentWrite
                | Verb::Block
        )
    }
}

/// Pure functions (RFC §2 `func`): set/graph operations, never math.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Func {
    Combine,
    Join,
    Intersect,
    Depend,
}

impl Func {
    pub fn long(self) -> &'static str {
        match self {
            Func::Combine => "combine",
            Func::Join => "join",
            Func::Intersect => "intersect",
            Func::Depend => "depend",
        }
    }

    pub fn from_name(s: &str) -> Option<Func> {
        Some(match s {
            "combine" => Func::Combine,
            "join" => Func::Join,
            "intersect" => Func::Intersect,
            "depend" => Func::Depend,
            _ => return None,
        })
    }
}

/// A call argument (RFC §2 `arg`). Verbs use `key=value`; pure funcs in the §4
/// example use positional operands, so both forms are accepted.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Arg {
    Named { key: String, value: Operand },
    Positional(Operand),
}

/// An assignment expression (RFC §2 `expression`): an `action` (verb) or an
/// `evaluation` (pure func).
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Expr {
    Action { verb: Verb, args: Vec<Arg> },
    Eval { func: Func, args: Vec<Arg> },
}

/// A generic call used as a dataflow term (e.g. `depend(%3,%4)`, `target(...)`).
/// Unlike [`Expr`], the name is unrestricted because RFC §4 uses `target(...)`,
/// which is neither a verb nor a func.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Call {
    pub name: String,
    pub args: Vec<Arg>,
}

/// A dataflow operator (RFC §2 `dataflow`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Dataflow {
    /// `→` — output of lhs feeds input of rhs.
    Then,
    /// `∵` — rhs is the justification of lhs.
    Because,
}

/// One side of a dataflow relation: an operand or a call.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FlowTerm {
    Operand(Operand),
    Call(Call),
}

/// Gate identifiers (RFC §2 `gate_name`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GateName {
    Artifact,
    English,
    NoCjk,
    Ci,
    Bench,
    Parse,
    Commit,
}

impl GateName {
    pub fn name(self) -> &'static str {
        match self {
            GateName::Artifact => "artifact",
            GateName::English => "english",
            GateName::NoCjk => "no_cjk",
            GateName::Ci => "ci",
            GateName::Bench => "bench",
            GateName::Parse => "parse",
            GateName::Commit => "commit",
        }
    }

    pub fn from_name(s: &str) -> Option<GateName> {
        Some(match s {
            "artifact" => GateName::Artifact,
            "english" => GateName::English,
            "no_cjk" => GateName::NoCjk,
            "ci" => GateName::Ci,
            "bench" => GateName::Bench,
            "parse" => GateName::Parse,
            "commit" => GateName::Commit,
            _ => return None,
        })
    }
}

/// Gate states (RFC §2 `gate_state`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GateState {
    Pass,
    Fail,
    Warn,
    Skip,
}

impl GateState {
    pub fn name(self) -> &'static str {
        match self {
            GateState::Pass => "pass",
            GateState::Fail => "fail",
            GateState::Warn => "warn",
            GateState::Skip => "skip",
        }
    }

    pub fn from_name(s: &str) -> Option<GateState> {
        Some(match s {
            "pass" => GateState::Pass,
            "fail" => GateState::Fail,
            "warn" => GateState::Warn,
            "skip" => GateState::Skip,
            _ => return None,
        })
    }
}

/// An SSA assignment line (RFC §2 `ssa_assignment`), with optional annotation
/// (`; k=v`) and optional `∵` justification (RFC §4 `%6 = merge(...) ∵ %3`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Assign {
    pub var: Var,
    pub expr: Expr,
    pub annotation: Vec<(String, Operand)>,
    pub because: Option<Operand>,
}

/// A gate statement (RFC §2 `gate`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GateStmt {
    pub name: GateName,
    pub state: GateState,
    pub because: Option<Operand>,
}

/// A dataflow relation or a `R:plan` schedule (`→ target`). `lhs` is `None`
/// for a bare schedule.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FlowStmt {
    pub lhs: Option<FlowTerm>,
    pub op: Dataflow,
    pub rhs: FlowTerm,
}

/// One line within a frame (RFC §2 `line`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Line {
    Assign(Assign),
    Gate(GateStmt),
    Flow(FlowStmt),
}

/// A register-tagged frame (RFC §2 `frame`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Frame {
    pub register: Register,
    pub lines: Vec<Line>,
}

/// A full V1 message (RFC §2 `message`): one or more frames.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Message {
    pub frames: Vec<Frame>,
}

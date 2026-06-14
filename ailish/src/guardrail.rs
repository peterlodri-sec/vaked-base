//! Register-monad guardrail (RFC §3, Phase B).
//!
//! Validates the structural rules each register imposes on its lines, and
//! computes the **freeze invariant**: if any `gate(*:fail)` is live, the
//! interpreter must freeze before executing any `R:commit` line and require a
//! human override. This is the merge-to-main classifier block the protocol was
//! designed around (RFC §3 invariant).

use crate::ast::*;

/// A single §3 rule violation.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Violation {
    pub register: Register,
    pub frame_index: usize,
    pub line_index: Option<usize>,
    pub rule: &'static str,
    pub detail: String,
}

/// The result of running the guardrail over a message.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GuardrailReport {
    pub violations: Vec<Violation>,
    /// `true` when a live `gate(*:fail)` means at least one `R:commit` line must
    /// be frozen pending human override.
    pub frozen: bool,
    /// Gate names observed in a `fail` state.
    pub live_fail_gates: Vec<GateName>,
    /// `(frame_index, line_index)` of each `R:commit` action line that is frozen.
    pub frozen_commit_lines: Vec<(usize, usize)>,
}

impl GuardrailReport {
    /// No §3 violations (says nothing about the freeze state).
    pub fn ok(&self) -> bool {
        self.violations.is_empty()
    }
}

fn is_commit_action(line: &Line) -> bool {
    matches!(
        line,
        Line::Assign(Assign {
            expr: Expr::Action {
                verb: Verb::Commit | Verb::Merge | Verb::Open,
                ..
            },
            ..
        })
    )
}

fn frame_has_gate(frame: &Frame, want: impl Fn(&GateStmt) -> bool) -> bool {
    frame
        .lines
        .iter()
        .any(|l| matches!(l, Line::Gate(g) if want(g)))
}

/// Run the §3 register-monad checks and compute the freeze invariant.
pub fn check(msg: &Message) -> GuardrailReport {
    let mut violations = Vec::new();

    // Global gate scan.
    let mut live_fail_gates = Vec::new();
    let mut has_ci_pass = false;
    for frame in &msg.frames {
        for line in &frame.lines {
            if let Line::Gate(g) = line {
                if g.state == GateState::Fail && !live_fail_gates.contains(&g.name) {
                    live_fail_gates.push(g.name);
                }
                if g.name == GateName::Ci && g.state == GateState::Pass {
                    has_ci_pass = true;
                }
            }
        }
    }
    let any_fail = !live_fail_gates.is_empty();

    // Per-register structural rules (§3 table).
    for (fi, frame) in msg.frames.iter().enumerate() {
        match frame.register {
            Register::Think | Register::Review => {
                for (li, line) in frame.lines.iter().enumerate() {
                    if let Line::Assign(Assign {
                        expr: Expr::Action { verb, .. },
                        ..
                    }) = line
                    {
                        if verb.is_side_effecting() {
                            violations.push(Violation {
                                register: frame.register,
                                frame_index: fi,
                                line_index: Some(li),
                                rule: "no-side-effects",
                                detail: format!(
                                    "{} may not contain the side-effecting verb `{}`",
                                    frame.register.long(),
                                    verb.name()
                                ),
                            });
                        }
                    }
                }
            }
            Register::Plan => {
                for (li, line) in frame.lines.iter().enumerate() {
                    if let Line::Assign(Assign {
                        expr: Expr::Action { verb, .. },
                        ..
                    }) = line
                    {
                        if verb.is_side_effecting() {
                            violations.push(Violation {
                                register: Register::Plan,
                                frame_index: fi,
                                line_index: Some(li),
                                rule: "plan-no-direct-side-effect",
                                detail: format!(
                                    "R:plan must only schedule; it may not invoke `{}` directly",
                                    verb.name()
                                ),
                            });
                        }
                    }
                }
            }
            Register::Risk => {
                let has_fail_gate = frame_has_gate(frame, |g| g.state == GateState::Fail);
                let has_mitigation = frame.lines.iter().any(|l| {
                    matches!(
                        l,
                        Line::Assign(Assign {
                            expr: Expr::Action {
                                verb: Verb::CheckPermission | Verb::Block,
                                ..
                            },
                            ..
                        })
                    )
                });
                if !frame.lines.is_empty() && !has_fail_gate && !has_mitigation {
                    violations.push(Violation {
                        register: Register::Risk,
                        frame_index: fi,
                        line_index: None,
                        rule: "risk-must-not-pass-silently",
                        detail: "R:risk must emit a gate(*:fail) or a mitigation step \
                                 (check_permission / block)"
                            .to_string(),
                    });
                }
            }
            Register::Artifact => {
                let asserts_posture = frame_has_gate(frame, |g| {
                    matches!(g.name, GateName::English | GateName::NoCjk)
                });
                if !frame.lines.is_empty() && !asserts_posture {
                    violations.push(Violation {
                        register: Register::Artifact,
                        frame_index: fi,
                        line_index: None,
                        rule: "artifact-must-assert-posture",
                        detail: "R:artifact must assert an `english` or `no_cjk` posture"
                            .to_string(),
                    });
                }
            }
            Register::Bench => {
                for (li, line) in frame.lines.iter().enumerate() {
                    if let Line::Assign(Assign {
                        expr:
                            Expr::Action {
                                verb: Verb::Test | Verb::Build,
                                ..
                            },
                        annotation,
                        ..
                    }) = line
                    {
                        if annotation.is_empty() {
                            violations.push(Violation {
                                register: Register::Bench,
                                frame_index: fi,
                                line_index: Some(li),
                                rule: "bench-metrics-required",
                                detail: "R:bench test/build lines must bind metrics in an \
                                         annotation (e.g. `; pass=61`)"
                                    .to_string(),
                            });
                        }
                    }
                }
            }
            Register::Commit => {
                let has_commit_action = frame.lines.iter().any(is_commit_action);
                if has_commit_action && !has_ci_pass {
                    violations.push(Violation {
                        register: Register::Commit,
                        frame_index: fi,
                        line_index: None,
                        rule: "commit-requires-ci-pass",
                        detail: "R:commit must be preceded by gate(ci:pass) in dataflow"
                            .to_string(),
                    });
                }
            }
            Register::Tool => { /* actions are always bound to %N by the grammar */ }
        }
    }

    // Freeze invariant: any live fail gate freezes every R:commit action line.
    let mut frozen_commit_lines = Vec::new();
    if any_fail {
        for (fi, frame) in msg.frames.iter().enumerate() {
            if frame.register == Register::Commit {
                for (li, line) in frame.lines.iter().enumerate() {
                    if is_commit_action(line) {
                        frozen_commit_lines.push((fi, li));
                    }
                }
            }
        }
    }
    let frozen = !frozen_commit_lines.is_empty();

    GuardrailReport {
        violations,
        frozen,
        live_fail_gates,
        frozen_commit_lines,
    }
}

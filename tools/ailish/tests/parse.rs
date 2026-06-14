//! Integration tests for the AI-lish V1 parser + guardrail.
//!
//! Authored PURELY from the normative spec
//! (`docs/ailish/2026-06-14-ailish-v1-rfc.md`) and the public-API contract in
//! (`docs/superpowers/plans/2026-06-14-ailish-v1-sdd.md`). No implementation
//! source was consulted. These tests are written to COMPILE against that exact
//! contract once an `src/` implementation exists; they are not expected to run
//! before then.
//!
//! Spec anchors exercised here:
//!   §2  grammar EBNF (registers, SSA, `→`/`∵`, typed atoms, verb/func/gate vocab)
//!   §3  register-monad rules (May / MUST / MUST NOT) + freeze invariant
//!   §4  lowering example (MUST parse exactly)
//!   §5  compaction map (`[R:bench]↔[!B]`, `combine(↔&(`, `intersect(↔^(`)

use ailish::{
    parse_message, validate, is_frozen, Action, Atom, Evaluation, Expression,
    Frame, Func, Gate, GateName, GateState, Line, Literal, Operand, Register, Schedule, SsaAssign,
    Stmt, Value, Variable, Verb,
};

// ---------------------------------------------------------------------------
// §4 — the canonical lowering example, as a single AI-lish V1 message.
// ---------------------------------------------------------------------------

/// The exact V1 SSA graph from §4 of the RFC.
const EXAMPLE_V4: &str = r#"[R:bench]  %0 = fetch(pr=205, scope="scalars")
           %1 = test(target=%0) ; pass=61
           %2 = build(target=%0, kind="rust") ; duration_s=22
           %3 = combine(%1, %2)
           gate(ci:pass) ∵ %3
[R:risk]   %4 = check_permission(verb="merge", tool=`gh`) ; state="classifier_blocked"
           gate(commit:fail) ∵ %4
[R:plan]   depend(%3, %4) → target(user_action="paste_merge_cmd")
           %5 = launch_agent(scope="aggregates", base=%0)
[R:commit] %6 = merge(pr=205) ∵ %3"#;

// ---------------------------------------------------------------------------
// §4 structural facts
// ---------------------------------------------------------------------------

#[test]
fn example_parses_into_four_register_frames() {
    let frames = parse_message(EXAMPLE_V4).expect("§4 example must parse");
    // The §4 V1 block contains four register frames, in order.
    assert_eq!(frames.len(), 4, "§4 example has 4 register frames");
    assert_eq!(frames[0].register, Register::Bench);
    assert_eq!(frames[1].register, Register::Risk);
    assert_eq!(frames[2].register, Register::Plan);
    assert_eq!(frames[3].register, Register::Commit);
}

#[test]
fn example_bench_frame_line_count_and_shape() {
    let frames = parse_message(EXAMPLE_V4).unwrap();
    let bench = &frames[0];
    // %0..%3 assignments + one gate stmt = 5 lines.
    assert_eq!(bench.lines.len(), 5);
}

#[test]
fn fetch_is_ssa_assign_with_verb_fetch() {
    let frames = parse_message(EXAMPLE_V4).unwrap();
    let bench = &frames[0];

    match &bench.lines[0] {
        Line::Assign(SsaAssign { var, expr, .. }) => {
            assert_eq!(*var, Variable(0), "%0 = fetch(...)");
            match expr {
                Expression::Action(Action { verb, args }) => {
                    assert_eq!(*verb, Verb::Fetch);
                    // fetch(pr=205, scope="scalars")
                    assert_eq!(args.len(), 2);
                    assert_eq!(args[0].key, "pr");
                    assert_eq!(args[0].value, Value::Atom(Atom::Literal(Literal::Number(205.0))));
                    assert_eq!(args[1].key, "scope");
                    assert_eq!(
                        args[1].value,
                        Value::Atom(Atom::Literal(Literal::Quoted("scalars".into())))
                    );
                }
                other => panic!("%0 should be an Action(fetch), got {other:?}"),
            }
        }
        other => panic!("first bench line should be an SsaAssign, got {other:?}"),
    }
}

#[test]
fn test_line_binds_metric_in_annotation() {
    let frames = parse_message(EXAMPLE_V4).unwrap();
    let bench = &frames[0];
    // %1 = test(target=%0) ; pass=61
    match &bench.lines[1] {
        Line::Assign(SsaAssign { var, expr, annotation }) => {
            assert_eq!(*var, Variable(1));
            match expr {
                Expression::Action(Action { verb, args }) => {
                    assert_eq!(*verb, Verb::Test);
                    assert_eq!(args[0].key, "target");
                    assert_eq!(args[0].value, Value::Var(Variable(0)));
                }
                other => panic!("expected Action(test), got {other:?}"),
            }
            // annotation: pass=61
            assert_eq!(annotation.len(), 1);
            assert_eq!(annotation[0].key, "pass");
            assert_eq!(
                annotation[0].value,
                Value::Atom(Atom::Literal(Literal::Number(61.0)))
            );
        }
        other => panic!("expected SsaAssign, got {other:?}"),
    }
}

#[test]
fn combine_is_a_pure_evaluation() {
    let frames = parse_message(EXAMPLE_V4).unwrap();
    let bench = &frames[0];
    // %3 = combine(%1, %2)
    match &bench.lines[3] {
        Line::Assign(SsaAssign { var, expr, .. }) => {
            assert_eq!(*var, Variable(3));
            match expr {
                Expression::Eval(Evaluation { func, args }) => {
                    assert_eq!(*func, Func::Combine);
                    assert_eq!(args.len(), 2);
                    assert_eq!(args[0].value, Value::Var(Variable(1)));
                    assert_eq!(args[1].value, Value::Var(Variable(2)));
                }
                other => panic!("combine() must be an Eval, got {other:?}"),
            }
        }
        other => panic!("expected SsaAssign, got {other:?}"),
    }
}

#[test]
fn bench_gate_ci_pass_justified_by_var3() {
    let frames = parse_message(EXAMPLE_V4).unwrap();
    let bench = &frames[0];
    // gate(ci:pass) ∵ %3
    match &bench.lines[4] {
        Line::Stmt(Stmt::Gate(Gate { name, state, because })) => {
            assert_eq!(*name, GateName::Ci);
            assert_eq!(*state, GateState::Pass);
            assert_eq!(*because, Some(Operand::Var(Variable(3))));
        }
        other => panic!("last bench line should be a Gate, got {other:?}"),
    }
}

#[test]
fn risk_gate_commit_fail_parses_with_because_var() {
    let frames = parse_message(EXAMPLE_V4).unwrap();
    let risk = &frames[1];
    // gate(commit:fail) ∵ %4
    let gate = risk
        .lines
        .iter()
        .find_map(|l| match l {
            Line::Stmt(Stmt::Gate(g)) => Some(g),
            _ => None,
        })
        .expect("R:risk frame contains a gate");
    assert_eq!(gate.name, GateName::Commit);
    assert_eq!(gate.state, GateState::Fail);
    assert_eq!(gate.because, Some(Operand::Var(Variable(4))));
}

#[test]
fn risk_check_permission_uses_symbol_atom_for_gh() {
    let frames = parse_message(EXAMPLE_V4).unwrap();
    let risk = &frames[1];
    // %4 = check_permission(verb="merge", tool=`gh`) ; state="classifier_blocked"
    match &risk.lines[0] {
        Line::Assign(SsaAssign { var, expr, annotation }) => {
            assert_eq!(*var, Variable(4));
            match expr {
                Expression::Action(Action { verb, args }) => {
                    assert_eq!(*verb, Verb::CheckPermission);
                    // verb="merge" is a quoted literal, not the Verb enum.
                    assert_eq!(
                        args[0].value,
                        Value::Atom(Atom::Literal(Literal::Quoted("merge".into())))
                    );
                    // tool=`gh` is a backtick symbol atom.
                    assert_eq!(args[1].value, Value::Atom(Atom::Symbol("gh".into())));
                }
                other => panic!("expected Action(check_permission), got {other:?}"),
            }
            assert_eq!(annotation[0].key, "state");
            assert_eq!(
                annotation[0].value,
                Value::Atom(Atom::Literal(Literal::Quoted("classifier_blocked".into())))
            );
        }
        other => panic!("expected SsaAssign, got {other:?}"),
    }
}

#[test]
fn plan_frame_has_relation_with_depend_and_schedule() {
    let frames = parse_message(EXAMPLE_V4).unwrap();
    let plan = &frames[2];
    // depend(%3, %4) → target(user_action="paste_merge_cmd")
    // This is a relation whose lhs is the depend() eval feeding a schedule target,
    // followed by %5 = launch_agent(...).
    // The frame must carry a Schedule stmt (R:plan-only "→ target").
    let has_schedule = plan.lines.iter().any(|l| {
        matches!(
            l,
            Line::Stmt(Stmt::Schedule(Schedule {
                target: Action { verb: _, .. }
            }))
        )
    });
    assert!(has_schedule, "R:plan frame must contain a schedule (→ target)");

    // %5 = launch_agent(scope="aggregates", base=%0)
    let launch = plan.lines.iter().find_map(|l| match l {
        Line::Assign(a @ SsaAssign { var, .. }) if *var == Variable(5) => Some(a),
        _ => None,
    });
    let launch = launch.expect("R:plan frame binds %5");
    match &launch.expr {
        Expression::Action(Action { verb, args }) => {
            assert_eq!(*verb, Verb::LaunchAgent);
            assert_eq!(args[1].value, Value::Var(Variable(0)), "base=%0");
        }
        other => panic!("expected launch_agent action, got {other:?}"),
    }
}

#[test]
fn commit_frame_merge_justified_by_var3() {
    let frames = parse_message(EXAMPLE_V4).unwrap();
    let commit = &frames[3];
    // %6 = merge(pr=205) ∵ %3
    match &commit.lines[0] {
        Line::Assign(SsaAssign { var, expr, .. }) => {
            assert_eq!(*var, Variable(6));
            match expr {
                Expression::Action(Action { verb, .. }) => assert_eq!(*verb, Verb::Merge),
                other => panic!("expected merge action, got {other:?}"),
            }
        }
        other => panic!("expected SsaAssign, got {other:?}"),
    }
}

// ---------------------------------------------------------------------------
// §5 — compact and long forms parse to EQUAL ASTs.
// ---------------------------------------------------------------------------

#[test]
fn compact_register_equals_long_register() {
    // [R:bench] == [!B]
    let long = parse_message("[R:bench] %0 = test(target=%0) ; pass=61").unwrap();
    let compact = parse_message("[!B] %0 = test(target=%0) ; pass=61").unwrap();
    assert_eq!(long, compact);
}

#[test]
fn compact_combine_token_equals_long() {
    // combine( == &(
    let long = parse_message("[R:think] %2 = combine(%0, %1)").unwrap();
    let compact = parse_message("[!T] %2 = &(%0, %1)").unwrap();
    assert_eq!(long, compact);
}

#[test]
fn compact_intersect_token_equals_long() {
    // intersect( == ^(
    let long = parse_message("[R:think] %2 = intersect(%0, %1)").unwrap();
    let compact = parse_message("[!T] %2 = ^(%0, %1)").unwrap();
    assert_eq!(long, compact);
}

#[test]
fn full_example_compact_equals_long() {
    // The whole §4 example rendered compact must parse to the same AST as long.
    const EXAMPLE_COMPACT: &str = r#"[!B]  %0 = fetch(pr=205, scope="scalars")
           %1 = test(target=%0) ; pass=61
           %2 = build(target=%0, kind="rust") ; duration_s=22
           %3 = &(%1, %2)
           gate(ci:pass) ∵ %3
[!R]   %4 = check_permission(verb="merge", tool=`gh`) ; state="classifier_blocked"
           gate(commit:fail) ∵ %4
[!P]   depend(%3, %4) → target(user_action="paste_merge_cmd")
           %5 = launch_agent(scope="aggregates", base=%0)
[!C] %6 = merge(pr=205) ∵ %3"#;

    let long = parse_message(EXAMPLE_V4).unwrap();
    let compact = parse_message(EXAMPLE_COMPACT).unwrap();
    assert_eq!(long, compact, "compact form must lower to the same AST as long");
}

// ---------------------------------------------------------------------------
// §2 — typed atoms distinguish correctly.
// ---------------------------------------------------------------------------

/// Pull the first arg value of the first assignment's expression.
fn first_arg_value(src: &str) -> Value {
    let frames = parse_message(src).expect("must parse");
    match &frames[0].lines[0] {
        Line::Assign(SsaAssign { expr, .. }) => match expr {
            Expression::Action(Action { args, .. }) => args[0].value.clone(),
            Expression::Eval(Evaluation { args, .. }) => args[0].value.clone(),
        },
        other => panic!("expected an assignment, got {other:?}"),
    }
}

#[test]
fn env_atom_is_typed_env() {
    // $TELEGRAM_TOKEN → Atom::Env
    let v = first_arg_value(r#"[R:tool] %0 = read(secret=$TELEGRAM_TOKEN)"#);
    assert_eq!(v, Value::Atom(Atom::Env("TELEGRAM_TOKEN".into())));
}

#[test]
fn path_atom_is_typed_path() {
    // a path → Atom::Path
    let v = first_arg_value(r#"[R:tool] %0 = read(file=src/lib.rs)"#);
    assert_eq!(v, Value::Atom(Atom::Path("src/lib.rs".into())));
}

#[test]
fn symbol_atom_is_typed_symbol() {
    // `gh` → Atom::Symbol
    let v = first_arg_value(r#"[R:tool] %0 = check_permission(tool=`gh`)"#);
    assert_eq!(v, Value::Atom(Atom::Symbol("gh".into())));
}

#[test]
fn quoted_literal_atom() {
    // "x" → Atom::Literal(Literal::Quoted)
    let v = first_arg_value(r#"[R:tool] %0 = write(content="x")"#);
    assert_eq!(v, Value::Atom(Atom::Literal(Literal::Quoted("x".into()))));
}

#[test]
fn number_literal_atom() {
    // 61 → Atom::Literal(Literal::Number)
    let v = first_arg_value(r#"[R:tool] %0 = test(pass=61)"#);
    assert_eq!(v, Value::Atom(Atom::Literal(Literal::Number(61.0))));
}

#[test]
fn bool_literal_atom() {
    // true → Atom::Literal(Literal::Bool)
    let v = first_arg_value(r#"[R:tool] %0 = test(green=true)"#);
    assert_eq!(v, Value::Atom(Atom::Literal(Literal::Bool(true))));
}

// ---------------------------------------------------------------------------
// §2 — malformed frames are rejected.
// ---------------------------------------------------------------------------

#[test]
fn malformed_frame_returns_err() {
    // No register header, unbalanced parens — not a valid frame.
    assert!(parse_message("%0 = fetch(pr=205").is_err());
}

#[test]
fn unknown_register_returns_err() {
    // R:bogus is not in the §2 register set.
    assert!(parse_message("[R:bogus] %0 = fetch(pr=205)").is_err());
}

#[test]
fn unknown_verb_returns_err() {
    // teleport is not in the §2 verb vocabulary.
    assert!(parse_message("[R:tool] %0 = teleport(pr=205)").is_err());
}

// ---------------------------------------------------------------------------
// §3 — register-monad rules: valid passes validate, violation returns Err
// carrying the offending register.
// ---------------------------------------------------------------------------

fn offending_registers(frames: &[Frame]) -> Vec<Register> {
    match validate(frames) {
        Ok(()) => Vec::new(),
        Err(errors) => errors.iter().map(|e| e.register.clone()).collect(),
    }
}

#[test]
fn think_valid_evaluation_passes() {
    // R:think MAY contain evaluations / relations.
    let frames = parse_message("[R:think] %2 = combine(%0, %1)").unwrap();
    assert!(validate(&frames).is_ok());
}

#[test]
fn think_side_effecting_verb_violates() {
    // R:think MUST NOT contain side-effecting verbs (merge).
    let frames = parse_message("[R:think] %0 = merge(pr=205)").unwrap();
    let offenders = offending_registers(&frames);
    assert!(
        offenders.contains(&Register::Think),
        "merge() inside R:think must be flagged on R:think, got {offenders:?}"
    );
}

#[test]
fn plan_schedule_only_passes() {
    // R:plan MAY schedule and depend(); a schedule-only frame validates.
    let frames =
        parse_message(r#"[R:plan] depend(%0) → target(user_action="paste_merge_cmd")"#).unwrap();
    assert!(validate(&frames).is_ok());
}

#[test]
fn plan_direct_side_effect_violates() {
    // R:plan MUST NOT invoke a side-effecting verb directly.
    let frames = parse_message("[R:plan] %0 = merge(pr=205)").unwrap();
    assert!(offending_registers(&frames).contains(&Register::Plan));
}

#[test]
fn tool_action_binds_result_passes() {
    // R:tool MUST bind result to %N; this one does.
    let frames = parse_message("[R:tool] %0 = fetch(pr=205)").unwrap();
    assert!(validate(&frames).is_ok());
}

#[test]
fn risk_with_gate_fail_passes() {
    // R:risk MUST emit gate(*:fail) or a mitigation; this emits gate(commit:fail).
    let frames = parse_message(
        r#"[R:risk] %0 = check_permission(verb="merge", tool=`gh`)
           gate(commit:fail) ∵ %0"#,
    )
    .unwrap();
    assert!(validate(&frames).is_ok());
}

#[test]
fn risk_passing_silently_violates() {
    // R:risk MUST NOT pass silently (no gate(*:fail) and no mitigation).
    let frames = parse_message(r#"[R:risk] %0 = check_permission(verb="merge", tool=`gh`)"#).unwrap();
    assert!(
        offending_registers(&frames).contains(&Register::Risk),
        "a silent R:risk frame must be flagged"
    );
}

#[test]
fn artifact_asserts_posture_passes() {
    // R:artifact MUST assert no_cjk / english posture.
    let frames = parse_message("[R:artifact] gate(no_cjk:pass)").unwrap();
    assert!(validate(&frames).is_ok());
}

#[test]
fn commit_preceded_by_ci_pass_passes() {
    // R:commit MUST be preceded by gate(ci:pass) in dataflow and not run under a
    // live gate(*:fail).
    let frames = parse_message(
        r#"[R:bench] %0 = combine(%1, %2)
           gate(ci:pass) ∵ %0
[R:commit] %1 = merge(pr=205) ∵ %0"#,
    )
    .unwrap();
    assert!(validate(&frames).is_ok());
}

#[test]
fn commit_under_live_fail_gate_violates() {
    // R:commit MUST NOT run if any upstream gate(*:fail) is live.
    let frames = parse_message(
        r#"[R:risk] %0 = check_permission(verb="merge", tool=`gh`)
           gate(commit:fail) ∵ %0
[R:commit] %1 = merge(pr=205) ∵ %0"#,
    )
    .unwrap();
    assert!(offending_registers(&frames).contains(&Register::Commit));
}

#[test]
fn review_must_not_mutate_state() {
    // R:review MUST NOT mutate state (no side-effecting verbs).
    let frames = parse_message("[R:review] %0 = write(file=src/lib.rs)").unwrap();
    assert!(offending_registers(&frames).contains(&Register::Review));
}

#[test]
fn bench_test_action_passes() {
    // R:bench MAY contain test/build actions with metrics in annotation.
    let frames = parse_message("[R:bench] %0 = test(target=%1) ; pass=61").unwrap();
    assert!(validate(&frames).is_ok());
}

// ---------------------------------------------------------------------------
// §3 freeze invariant — is_frozen.
// ---------------------------------------------------------------------------

#[test]
fn is_frozen_true_when_commit_fail_precedes_commit_merge() {
    // A live gate(commit:fail) before an R:commit merge(...) line → frozen.
    let frames = parse_message(
        r#"[R:risk] %4 = check_permission(verb="merge", tool=`gh`)
           gate(commit:fail) ∵ %4
[R:commit] %6 = merge(pr=205) ∵ %4"#,
    )
    .unwrap();
    assert!(is_frozen(&frames), "live gate(commit:fail) must freeze R:commit");
}

#[test]
fn is_frozen_false_when_only_ci_pass() {
    // A clean message with gate(ci:pass) only → not frozen.
    let frames = parse_message(
        r#"[R:bench] %0 = combine(%1, %2)
           gate(ci:pass) ∵ %0
[R:commit] %1 = merge(pr=205) ∵ %0"#,
    )
    .unwrap();
    assert!(!is_frozen(&frames), "gate(ci:pass) alone must not freeze");
}

#[test]
fn is_frozen_true_for_full_example() {
    // The §4 example carries a live gate(commit:fail) ahead of [R:commit].
    let frames = parse_message(EXAMPLE_V4).unwrap();
    assert!(is_frozen(&frames), "§4 example is frozen by gate(commit:fail)");
}

#[test]
fn is_frozen_uses_dataflow_correctly_for_relations() {
    // Sanity: a message with no R:commit line is never frozen, regardless of gates.
    let frames = parse_message(
        r#"[R:risk] %0 = check_permission(verb="merge", tool=`gh`)
           gate(commit:fail) ∵ %0"#,
    )
    .unwrap();
    assert!(!is_frozen(&frames), "no R:commit line → not frozen");
}

// ---------------------------------------------------------------------------
// Coverage added after the SDD completeness-critic pass.
// ---------------------------------------------------------------------------

#[test]
fn commit_without_ci_pass_violates() {
    // §3: R:commit MUST be preceded by gate(ci:pass) in dataflow.
    let frames = parse_message("[R:commit] %0 = merge(pr=1)").unwrap();
    let errs = validate(&frames).unwrap_err();
    assert!(
        errs.iter()
            .any(|e| e.register == Register::Commit && e.rule == "R:commit/requires-ci-pass"),
        "a commit with no upstream gate(ci:pass) must be flagged"
    );
}

#[test]
fn commit_with_prior_ci_pass_clears_prerequisite() {
    let frames = parse_message(
        "[R:bench] gate(ci:pass) ∵ %0\n[R:commit] %1 = merge(pr=1) ∵ %0",
    )
    .unwrap();
    assert!(validate(&frames).is_ok());
}

#[test]
fn all_compact_registers_equal_long_forms() {
    // §5: every compact register form parses identically to its long form.
    for (long, compact) in [
        ("R:think", "!T"),
        ("R:plan", "!P"),
        ("R:tool", "!X"),
        ("R:risk", "!R"),
        ("R:artifact", "!A"),
        ("R:commit", "!C"),
        ("R:review", "!V"),
        ("R:bench", "!B"),
    ] {
        let src_long = format!("[{long}] gate(ci:pass)");
        let src_compact = format!("[{compact}] gate(ci:pass)");
        assert_eq!(
            parse_message(&src_long).unwrap(),
            parse_message(&src_compact).unwrap(),
            "compact [{compact}] must equal long [{long}]"
        );
    }
}

#[test]
fn join_func_parses() {
    let frames = parse_message("[R:think] %0 = join(%1, %2)").unwrap();
    match &frames[0].lines[0] {
        Line::Assign(a) => match &a.expr {
            Expression::Eval(e) => assert_eq!(e.func, Func::Join),
            other => panic!("expected Eval(join), got {other:?}"),
        },
        other => panic!("expected assign, got {other:?}"),
    }
}

#[test]
fn warn_and_skip_gate_states_parse() {
    for (state_src, state) in [("warn", GateState::Warn), ("skip", GateState::Skip)] {
        let frames = parse_message(&format!("[R:review] gate(bench:{state_src})")).unwrap();
        match &frames[0].lines[0] {
            Line::Stmt(Stmt::Gate(g)) => {
                assert_eq!(g.state, state);
                assert_eq!(g.name, GateName::Bench);
            }
            other => panic!("expected gate, got {other:?}"),
        }
    }
}

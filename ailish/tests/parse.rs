//! Parser tests (RFC §2, §4 example).

use ailish::*;

#[test]
fn parses_rfc_example_into_four_frames() {
    let msg = parse_message(EXAMPLE_V1).expect("RFC §4 example must parse");
    assert_eq!(msg.frames.len(), 4);
    assert_eq!(msg.frames[0].register, Register::Bench);
    assert_eq!(msg.frames[1].register, Register::Risk);
    assert_eq!(msg.frames[2].register, Register::Plan);
    assert_eq!(msg.frames[3].register, Register::Commit);
}

#[test]
fn frame_line_counts_match_example() {
    let msg = parse_message(EXAMPLE_V1).unwrap();
    assert_eq!(msg.frames[0].lines.len(), 5); // %0..%3 + gate
    assert_eq!(msg.frames[1].lines.len(), 2); // %4 + gate
    assert_eq!(msg.frames[2].lines.len(), 2); // depend->target + %5
    assert_eq!(msg.frames[3].lines.len(), 1); // %6 = merge
}

#[test]
fn first_assignment_is_typed_action_with_named_args() {
    let msg = parse_message(EXAMPLE_V1).unwrap();
    match &msg.frames[0].lines[0] {
        Line::Assign(a) => {
            assert_eq!(a.var, Var(0));
            match &a.expr {
                Expr::Action { verb, args } => {
                    assert_eq!(*verb, Verb::Fetch);
                    assert_eq!(args.len(), 2);
                    assert_eq!(
                        args[0],
                        Arg::Named {
                            key: "pr".into(),
                            value: Operand::Atom(Atom::Number("205".into()))
                        }
                    );
                    assert_eq!(
                        args[1],
                        Arg::Named {
                            key: "scope".into(),
                            value: Operand::Atom(Atom::Quoted("scalars".into()))
                        }
                    );
                }
                other => panic!("expected action, got {other:?}"),
            }
        }
        other => panic!("expected assignment, got {other:?}"),
    }
}

#[test]
fn combine_is_pure_eval_with_positional_vars() {
    let msg = parse_message(EXAMPLE_V1).unwrap();
    match &msg.frames[0].lines[3] {
        Line::Assign(a) => match &a.expr {
            Expr::Eval { func, args } => {
                assert_eq!(*func, Func::Combine);
                assert_eq!(args[0], Arg::Positional(Operand::Var(Var(1))));
                assert_eq!(args[1], Arg::Positional(Operand::Var(Var(2))));
            }
            other => panic!("expected eval, got {other:?}"),
        },
        other => panic!("expected assignment, got {other:?}"),
    }
}

#[test]
fn gate_carries_justification() {
    let msg = parse_message(EXAMPLE_V1).unwrap();
    match &msg.frames[0].lines[4] {
        Line::Gate(g) => {
            assert_eq!(g.name, GateName::Ci);
            assert_eq!(g.state, GateState::Pass);
            assert_eq!(g.because, Some(Operand::Var(Var(3))));
        }
        other => panic!("expected gate, got {other:?}"),
    }
}

#[test]
fn schedule_uses_dataflow_and_generic_target_call() {
    let msg = parse_message(EXAMPLE_V1).unwrap();
    match &msg.frames[2].lines[0] {
        Line::Flow(f) => {
            assert_eq!(f.op, Dataflow::Then);
            match &f.lhs {
                Some(FlowTerm::Call(c)) => assert_eq!(c.name, "depend"),
                other => panic!("expected depend() lhs, got {other:?}"),
            }
            match &f.rhs {
                FlowTerm::Call(c) => assert_eq!(c.name, "target"),
                other => panic!("expected target() rhs, got {other:?}"),
            }
        }
        other => panic!("expected flow, got {other:?}"),
    }
}

#[test]
fn assignment_justification_parses() {
    let msg = parse_message(EXAMPLE_V1).unwrap();
    match &msg.frames[3].lines[0] {
        Line::Assign(a) => {
            assert_eq!(a.var, Var(6));
            assert_eq!(a.because, Some(Operand::Var(Var(3))));
            match &a.expr {
                Expr::Action { verb, .. } => assert_eq!(*verb, Verb::Merge),
                other => panic!("expected merge action, got {other:?}"),
            }
        }
        other => panic!("expected assignment, got {other:?}"),
    }
}

#[test]
fn compact_register_and_func_forms_parse_equally() {
    let long = "[R:bench] %3 = combine(%1, %2)\n";
    let compact = "[!B] %3 = &(%1, %2)\n";
    assert_eq!(
        parse_message(long).unwrap(),
        parse_message(compact).unwrap()
    );
}

#[test]
fn typed_atoms_are_distinguished() {
    let src = "[R:tool] %0 = write(p=path/to.rs, s=$TOKEN, sym=`gh`, q=\"x\", n=42, b=true)\n";
    let msg = parse_message(src).unwrap();
    let Line::Assign(a) = &msg.frames[0].lines[0] else {
        panic!("expected assignment");
    };
    let Expr::Action { args, .. } = &a.expr else {
        panic!("expected action");
    };
    let vals: Vec<&Operand> = args
        .iter()
        .map(|x| match x {
            Arg::Named { value, .. } => value,
            Arg::Positional(o) => o,
        })
        .collect();
    assert_eq!(vals[0], &Operand::Atom(Atom::Path("path/to.rs".into())));
    assert_eq!(vals[1], &Operand::Atom(Atom::Env("TOKEN".into())));
    assert_eq!(vals[2], &Operand::Atom(Atom::Symbol("gh".into())));
    assert_eq!(vals[3], &Operand::Atom(Atom::Quoted("x".into())));
    assert_eq!(vals[4], &Operand::Atom(Atom::Number("42".into())));
    assert_eq!(vals[5], &Operand::Atom(Atom::Bool(true)));
}

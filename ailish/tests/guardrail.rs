//! Guardrail tests (RFC §3 register monads + freeze invariant).

use ailish::*;

#[test]
fn rfc_example_passes_and_freezes_commit() {
    let msg = parse_message(EXAMPLE_V1).unwrap();
    let report = guardrail_check(&msg);
    assert!(
        report.ok(),
        "unexpected violations: {:?}",
        report.violations
    );
    // gate(commit:fail) is live, so the R:commit merge line must freeze.
    assert!(
        report.frozen,
        "merge should be frozen by live gate(commit:fail)"
    );
    assert!(report.live_fail_gates.contains(&GateName::Commit));
    assert_eq!(report.frozen_commit_lines, vec![(3, 0)]);
}

#[test]
fn think_may_not_side_effect() {
    let msg = parse_message("[R:think] %0 = write(path=lib.rs)\n").unwrap();
    let report = guardrail_check(&msg);
    assert!(!report.ok());
    assert_eq!(report.violations[0].rule, "no-side-effects");
    assert_eq!(report.violations[0].register, Register::Think);
}

#[test]
fn review_may_not_mutate_state() {
    let msg = parse_message("[R:review] %0 = merge(pr=1)\n").unwrap();
    let report = guardrail_check(&msg);
    assert!(!report.ok());
    assert_eq!(report.violations[0].rule, "no-side-effects");
}

#[test]
fn plan_may_launch_agents_but_not_merge() {
    let ok = parse_message("[R:plan] %0 = launch_agent(scope=\"x\")\n").unwrap();
    assert!(guardrail_check(&ok).ok());

    let bad = parse_message("[R:plan] %0 = merge(pr=1)\n").unwrap();
    let report = guardrail_check(&bad);
    assert!(!report.ok());
    assert_eq!(report.violations[0].rule, "plan-no-direct-side-effect");
}

#[test]
fn risk_must_not_pass_silently() {
    let bad = parse_message("[R:risk] %0 = read(path=x)\n").unwrap();
    let report = guardrail_check(&bad);
    assert!(!report.ok());
    assert_eq!(report.violations[0].rule, "risk-must-not-pass-silently");

    let ok = parse_message("[R:risk] gate(commit:fail) ∵ %0\n").unwrap();
    assert!(guardrail_check(&ok).ok());
}

#[test]
fn commit_requires_ci_pass() {
    // No gate(ci:pass), no fail gate: structural violation, not frozen.
    let msg = parse_message("[R:commit] %0 = merge(pr=1)\n").unwrap();
    let report = guardrail_check(&msg);
    assert!(!report.ok());
    assert_eq!(report.violations[0].rule, "commit-requires-ci-pass");
    assert!(!report.frozen);
}

#[test]
fn commit_with_ci_pass_and_no_fail_is_clean_and_unfrozen() {
    let src = "[R:bench] gate(ci:pass) ∵ %0\n[R:commit] %1 = merge(pr=1) ∵ %0\n";
    let msg = parse_message(src).unwrap();
    let report = guardrail_check(&msg);
    assert!(report.ok(), "violations: {:?}", report.violations);
    assert!(!report.frozen);
}

#[test]
fn bench_test_without_metrics_is_flagged() {
    let msg = parse_message("[R:bench] %0 = test(target=%1)\n").unwrap();
    let report = guardrail_check(&msg);
    assert!(!report.ok());
    assert_eq!(report.violations[0].rule, "bench-metrics-required");
}

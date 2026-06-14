//! Integration tests for `ailishfmt` (the §5 compaction formatter).
//!
//! Authored PURELY from the normative spec
//! (`docs/ailish/2026-06-14-ailish-v1-rfc.md` §4 example, §5 compaction map)
//! and the public-API contract in
//! (`docs/superpowers/plans/2026-06-14-ailish-v1-sdd.md`). No implementation
//! source was consulted. Written to COMPILE against that exact contract once an
//! `src/` implementation exists.
//!
//! Properties exercised:
//!   idempotency : fmt(parse(fmt(x, m)), m) == fmt(x, m)   for m in {Long, Compact}
//!   round-trip  : parse(fmt(x, m)) == x                   (AST stable through fmt)
//!   compaction  : token_estimate(fmt(x, Compact)) < token_estimate(fmt(x, Long))

use ailish::{ailishfmt, parse_message, token_estimate, FmtMode};

/// The exact §4 V1 lowering example — the shared fixture for all fmt tests.
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

/// Parse the §4 example into the canonical fixture AST.
fn example_frames() -> Vec<ailish::Frame> {
    parse_message(EXAMPLE_V4).expect("§4 example must parse")
}

// ---------------------------------------------------------------------------
// Idempotency — fmt(parse(fmt(x, m)), m) == fmt(x, m)
// ---------------------------------------------------------------------------

#[test]
fn idempotent_long() {
    let f = example_frames();
    let once = ailishfmt(&f, FmtMode::Long);
    let twice = ailishfmt(&parse_message(&once).unwrap(), FmtMode::Long);
    assert_eq!(twice, once, "Long-form fmt must be idempotent");
}

#[test]
fn idempotent_compact() {
    let f = example_frames();
    let once = ailishfmt(&f, FmtMode::Compact);
    let twice = ailishfmt(&parse_message(&once).unwrap(), FmtMode::Compact);
    assert_eq!(twice, once, "Compact-form fmt must be idempotent");
}

// ---------------------------------------------------------------------------
// Round-trip — parse(fmt(x, m)) == x
// ---------------------------------------------------------------------------

#[test]
fn round_trip_long_preserves_ast() {
    let f = example_frames();
    let rendered = ailishfmt(&f, FmtMode::Long);
    let reparsed = parse_message(&rendered).unwrap();
    assert_eq!(reparsed, f, "Long fmt must round-trip the AST unchanged");
}

#[test]
fn round_trip_compact_preserves_ast() {
    let f = example_frames();
    let rendered = ailishfmt(&f, FmtMode::Compact);
    let reparsed = parse_message(&rendered).unwrap();
    assert_eq!(reparsed, f, "Compact fmt must round-trip the AST unchanged");
}

#[test]
fn long_and_compact_render_the_same_ast() {
    // Both formatter modes must describe the same underlying frames; parsing
    // either rendering yields the original AST.
    let f = example_frames();
    let long = parse_message(&ailishfmt(&f, FmtMode::Long)).unwrap();
    let compact = parse_message(&ailishfmt(&f, FmtMode::Compact)).unwrap();
    assert_eq!(long, compact);
    assert_eq!(long, f);
}

// ---------------------------------------------------------------------------
// Compaction shrinks — token_estimate(Compact) < token_estimate(Long)
// ---------------------------------------------------------------------------

#[test]
fn compact_form_shrinks_token_estimate() {
    let f = example_frames();
    let long_tokens = token_estimate(&ailishfmt(&f, FmtMode::Long));
    let compact_tokens = token_estimate(&ailishfmt(&f, FmtMode::Compact));
    assert!(
        compact_tokens < long_tokens,
        "compact form must cost fewer tokens: compact={compact_tokens} long={long_tokens}"
    );
}

#[test]
fn token_estimate_is_nonzero_for_example() {
    // Sanity: the proxy yields a positive count for a real message.
    let f = example_frames();
    assert!(token_estimate(&ailishfmt(&f, FmtMode::Long)) > 0);
}

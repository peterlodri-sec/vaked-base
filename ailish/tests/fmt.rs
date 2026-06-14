//! Formatter tests (RFC §5): idempotency, round-trip, and compaction savings.

use ailish::*;

#[test]
fn long_form_is_idempotent() {
    let once = format_message(EXAMPLE_V1, false).unwrap();
    let twice = format_message(&once, false).unwrap();
    assert_eq!(once, twice);
}

#[test]
fn compact_form_is_idempotent() {
    let once = format_message(EXAMPLE_V1, true).unwrap();
    let twice = format_message(&once, true).unwrap();
    assert_eq!(once, twice);
}

#[test]
fn render_round_trips_through_the_parser() {
    let msg = parse_message(EXAMPLE_V1).unwrap();
    let long = render(&msg, false);
    assert_eq!(parse_message(&long).unwrap(), msg);
    let compact = render(&msg, true);
    assert_eq!(parse_message(&compact).unwrap(), msg);
}

#[test]
fn long_and_compact_carry_the_same_ast() {
    let msg = parse_message(EXAMPLE_V1).unwrap();
    let from_long = parse_message(&render(&msg, false)).unwrap();
    let from_compact = parse_message(&render(&msg, true)).unwrap();
    assert_eq!(from_long, from_compact);
}

#[test]
fn compact_form_is_smaller() {
    let msg = parse_message(EXAMPLE_V1).unwrap();
    let long = render(&msg, false);
    let compact = render(&msg, true);
    assert!(
        compact.len() < long.len(),
        "compact {} should be fewer chars than long {}",
        compact.len(),
        long.len()
    );
    assert!(count_tokens(&compact) <= count_tokens(&long));
}

//! `ailish-tokenbench` — measures tokens-per-frame, long vs compact (RFC §5).
//!
//! Reads V1 from a FILE argument or uses the RFC §4 example, then reports
//! character and token counts for both rendered forms and the savings.

use ailish::{count_tokens, parse_message, render, EXAMPLE_V1};

fn main() {
    let src = match std::env::args().nth(1) {
        Some(p) => std::fs::read_to_string(&p).unwrap_or_else(|e| {
            eprintln!("ailish-tokenbench: cannot read {p}: {e}");
            std::process::exit(2);
        }),
        None => EXAMPLE_V1.to_string(),
    };

    let msg = match parse_message(&src) {
        Ok(m) => m,
        Err(e) => {
            eprintln!("ailish-tokenbench: {e}");
            std::process::exit(1);
        }
    };

    let long = render(&msg, false);
    let compact = render(&msg, true);

    let (lc, lt) = (long.len(), count_tokens(&long));
    let (cc, ct) = (compact.len(), count_tokens(&compact));

    println!("frames:  {}", msg.frames.len());
    println!("long:    {lc} chars, {lt} tokens");
    println!("compact: {cc} chars, {ct} tokens");

    let char_savings = 100.0 * (1.0 - cc as f64 / lc as f64);
    let tok_savings = 100.0 * (1.0 - ct as f64 / lt as f64);
    println!("savings: {char_savings:.1}% chars, {tok_savings:.1}% tokens");
}

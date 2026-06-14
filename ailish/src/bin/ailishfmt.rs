//! `ailishfmt` — idempotent AI-lish V1 formatter (RFC §5, Phase C).
//!
//! Reads V1 from a FILE argument or stdin, reparses, and re-emits in long
//! (default) or compact (`--compact`) form.

use std::io::{self, Read, Write};

fn main() {
    let mut compact = false;
    let mut path: Option<String> = None;

    for arg in std::env::args().skip(1) {
        match arg.as_str() {
            "--compact" | "-c" => compact = true,
            "--long" | "-l" => compact = false,
            "-h" | "--help" => {
                eprintln!(
                    "usage: ailishfmt [--compact|--long] [FILE]\n\
                     Reformats AI-lish V1 (from FILE or stdin) idempotently."
                );
                return;
            }
            other => path = Some(other.to_string()),
        }
    }

    let src = match path {
        Some(p) => match std::fs::read_to_string(&p) {
            Ok(s) => s,
            Err(e) => {
                eprintln!("ailishfmt: cannot read {p}: {e}");
                std::process::exit(2);
            }
        },
        None => {
            let mut s = String::new();
            if let Err(e) = io::stdin().read_to_string(&mut s) {
                eprintln!("ailishfmt: cannot read stdin: {e}");
                std::process::exit(2);
            }
            s
        }
    };

    match ailish::format_message(&src, compact) {
        Ok(out) => {
            let _ = io::stdout().write_all(out.as_bytes());
        }
        Err(e) => {
            eprintln!("ailishfmt: {e}");
            std::process::exit(1);
        }
    }
}

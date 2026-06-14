//! `ailishcheck` — validate AI-lish V1 graphs with the `ailish` parser + guardrail.
//!
//! Used by the ARP fine-tuning dataset harness (`tools/ail-dataset/`) to prove
//! every row's AI-lish V1 core parses and passes the §3 register-monad guardrail,
//! and that two forms (e.g. long vs compact) parse to the same graph.
//!
//! Usage:
//!   ailishcheck <file>          parse + guardrail-validate one V1 graph; exit 1 on failure
//!   ailishcheck -               read the graph from stdin
//!   ailishcheck --eq <a> <b>    parse both; exit 1 unless their ASTs are equal
//!
//! ARP behavioral primitives ([STRIDE: …], [T:N], [+]/[-]/[!], [BRANCH: …]) are
//! advisory (RFC 0009) and are NOT part of the V1 grammar — strip them before
//! passing a graph here (the dataset harness does this).

use std::io::Read;
use std::process::exit;

fn read_input(arg: &str) -> String {
    if arg == "-" {
        let mut s = String::new();
        std::io::stdin()
            .read_to_string(&mut s)
            .expect("read stdin");
        s
    } else {
        std::fs::read_to_string(arg).unwrap_or_else(|e| {
            eprintln!("ailishcheck: cannot read {arg}: {e}");
            exit(2);
        })
    }
}

/// Parse + guardrail-validate one graph. Returns true on success.
fn check_one(src: &str, label: &str) -> bool {
    match ailish::parse_message(src) {
        Ok(frames) => match ailish::validate(&frames) {
            Ok(()) => {
                println!(
                    "ok       {label}  ({} frames, frozen={})",
                    frames.len(),
                    ailish::is_frozen(&frames)
                );
                true
            }
            Err(errs) => {
                for e in &errs {
                    eprintln!("guardrail {label}: {e:?}");
                }
                false
            }
        },
        Err(e) => {
            eprintln!("parse    {label}: {e:?}");
            false
        }
    }
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match args.as_slice() {
        [flag, a, b] if flag == "--eq" => {
            let (ta, tb) = (read_input(a), read_input(b));
            match (ailish::parse_message(&ta), ailish::parse_message(&tb)) {
                (Ok(x), Ok(y)) if x == y => println!("ok       eq  {a} == {b}"),
                (Ok(_), Ok(_)) => {
                    eprintln!("eq       {a} != {b}: parsed graphs differ");
                    exit(1);
                }
                (ra, rb) => {
                    if let Err(e) = ra {
                        eprintln!("parse    {a}: {e:?}");
                    }
                    if let Err(e) = rb {
                        eprintln!("parse    {b}: {e:?}");
                    }
                    exit(1);
                }
            }
        }
        [one] => {
            if !check_one(&read_input(one), one) {
                exit(1);
            }
        }
        _ => {
            eprintln!("usage: ailishcheck <file|-> | --eq <a> <b>");
            exit(2);
        }
    }
}

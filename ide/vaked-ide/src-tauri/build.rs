fn main() {
    // Link libghostty only for the opt-in macOS embedded-terminal build.
    // See docs/terminal-embedding.md. The feature is OFF by default, so the
    // standard build (and CI) never touches this path.
    let ghostty = std::env::var("CARGO_FEATURE_GHOSTTY").is_ok();
    let macos = std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("macos");
    if ghostty && macos {
        link_libghostty();
    }

    tauri_build::build()
}

#[allow(dead_code)]
fn link_libghostty() {
    // 1) Explicit path to a local libghostty build.
    if let Ok(dir) = std::env::var("LIBGHOSTTY_PATH") {
        println!("cargo:rustc-link-search=native={dir}");
        println!("cargo:rustc-link-lib=dylib=ghostty");
    } else {
        // 2) pkg-config, if Ghostty is installed system-wide.
        match std::process::Command::new("pkg-config")
            .args(["--libs", "ghostty"])
            .output()
        {
            Ok(out) if out.status.success() => {
                let flags = String::from_utf8_lossy(&out.stdout);
                for tok in flags.split_whitespace() {
                    if let Some(p) = tok.strip_prefix("-L") {
                        println!("cargo:rustc-link-search=native={p}");
                    } else if let Some(l) = tok.strip_prefix("-l") {
                        println!("cargo:rustc-link-lib=dylib={l}");
                    }
                }
            }
            _ => {
                // 3) Opt-in feature with no lib found is a developer error, not
                // a CI break. Warn and let the linker surface missing symbols.
                println!(
                    "cargo:warning=--features ghostty set but libghostty not found; \
                     set LIBGHOSTTY_PATH=/path/to/ghostty/zig-out/lib"
                );
            }
        }
    }

    // Frameworks libghostty's Metal renderer needs on macOS.
    for fw in ["Metal", "QuartzCore", "AppKit", "CoreText", "CoreGraphics"] {
        println!("cargo:rustc-link-lib=framework={fw}");
    }
    println!("cargo:rerun-if-env-changed=LIBGHOSTTY_PATH");
}

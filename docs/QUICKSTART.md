# Vaked Quick Start

## Installation

To get started with Vaked, clone the repository and enter the development shell provided by Nix. The dev shell includes all required toolchains for Zig, BEAM/OTP, Rust, and supporting tools. Run `nix develop` to activate the environment, which provides the `vakedc` (Python) and `vakedz` (Zig) compilers alongside other dependencies. No global installation is required—everything runs within the sandboxed shell.

## Your First Declaration

Create a `.vaked` file in the `vaked/examples/` directory with a simple capability declaration. A minimal Vaked program declares a named service with one or more capabilities, which the compiler will parse, type-check, and lower into artifacts (Nix flake, Zig configs, eBPF policy). Run `vakedc parse <file>` or `vakedz parse <file>` to validate your syntax, then `vakedc check <file>` to verify the declaration against the type schema.

## Next Steps

Once your declaration is valid, run `vakedc lower <file>` to generate output artifacts: a typed capability graph, NixOS module stubs, and documentation. Consult `docs/context/PROJECT_CONTEXT.md` for the canonical project overview, `docs/language/0001-primer.md` for language design principles, and `vaked/examples/` for reference declarations. For protocol details, see `docs/protocol/` and the RFCs in `protocol/rfcs/`. To contribute language changes, use the `vaked-language-author` skill and follow the grammar-first convention.

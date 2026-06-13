{
  description = "vaked-ide dev shell";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    rust-overlay = {
      url = "github:oxalica/rust-overlay";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, rust-overlay }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in {
      devShells = forAllSystems (system:
        let
          pkgs = import nixpkgs {
            inherit system;
            overlays = [ rust-overlay.overlays.default ];
          };
          rustToolchain = pkgs.rust-bin.stable.latest.default.override {
            extensions = [ "rust-src" "rust-analyzer" ];
          };
          linuxDeps = pkgs.lib.optionals pkgs.stdenv.isLinux (with pkgs; [
            gtk3
            webkitgtk_4_1
            librsvg
            libayatana-appindicator
            libsoup_3
            pkg-config
          ]);
        in pkgs.mkShell {
          packages = with pkgs; [
            rustToolchain
            cargo-tauri
            nodejs_22
            python3
          ] ++ linuxDeps;

          shellHook = ''
            export VAKED_BASE="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
            export ANTHROPIC_API_KEY="''${ANTHROPIC_API_KEY:-}"
          '';
        });
    };
}

{
  description = "vaked-base — foundation monorepo for the Vaked agentic-runtime ecosystem";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f (import nixpkgs { inherit system; }));
    in
    {
      # Vaked declares → Nix materializes. The dev shell carries the toolchains
      # each layer of the mantra needs.
      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          name = "vaked-base";
          packages = with pkgs; [
            nixpkgs-fmt           # format this flake + future generated Nix
            zig_0_16              # Zig enforces — pinned 0.16.0 for the vakedc self-hosting port (also: sandboxd, agent-guardd, …)
            sqlite                # libsqlite3 + headers — vakedc `parse --sqlite` parity (3.51.2 via the locked nixpkgs rev)
            erlang                # OTP supervises — agent-supervisord control plane
            elixir
            rustc                 # CrabCC indexes — toolchain to build crabcc-labs/crabcc
            cargo
            git
            jq
            just
          ];
          shellHook = ''
            echo "vaked-base · Vaked declares · Nix materializes · OTP supervises · Zig enforces · eBPF testifies · CrabCC indexes · Surfaces reveal"
            echo "crabcc: $(command -v crabcc >/dev/null 2>&1 && crabcc --version || echo 'not installed — see CLAUDE.md patch-doctor')"
          '';
        };
      });

      formatter = forAllSystems (pkgs: pkgs.nixpkgs-fmt);
    };
}

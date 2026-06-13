{
  description = "vaked-base — foundation monorepo for the Vaked agentic-runtime ecosystem";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

    # Declarative disk partitioning for the materialization target(s).
    # Drives hosts/vakedos/disko.nix; consumed by nixos-anywhere at install time.
    disko.url = "github:nix-community/disko";
    disko.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs = { self, nixpkgs, disko }:
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
            zig                   # Zig enforces — sandboxd, agent-guardd, eventd, …
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

      # vakedc-zig: the Zig-native compiler-parser (v0.1.0, 0018).
      # `nix build .#vakedc-zig` produces the binary at result/bin/vakedc-zig.
      # No external Zig package deps — builds hermetically from zig/vakedc/.
      packages = forAllSystems (pkgs: {
        vakedc-zig = pkgs.stdenv.mkDerivation {
          pname = "vakedc-zig";
          version = "0.1.0";
          src = ./zig/vakedc;
          nativeBuildInputs = [ pkgs.zig ];
          buildPhase = ''
            export HOME=$TMPDIR
            zig build -Doptimize=ReleaseSafe
          '';
          installPhase = ''
            mkdir -p $out/bin
            cp zig-out/bin/vakedc-zig $out/bin/
          '';
          doCheck = true;
          checkPhase = ''
            export HOME=$TMPDIR
            zig build test
          '';
          meta.description = "vakedc-zig — Zig-native Vaked compiler-parser (parse stage, v0.1.0)";
        };
      });

      # Nix materializes. `vakedos` is the bare-metal materialization target — the
      # NixOS substrate a Vaked runtime's emitted nixosModules.<runtime> will later
      # be layered onto (docs/language/0012-lowering.md §4.3). Today it is a clean,
      # EPYC/ECC-tuned Nix build host; no runtime daemons are wired (they are stubs,
      # see docs/runtime/README.md). See hosts/vakedos/README.md for the Vultr
      # bare-metal install runbook.
      # No `system` here: the host pins its platform (and the global -march) via
      # nixpkgs.hostPlatform inside configuration.nix, so it owns that one option.
      nixosConfigurations.vakedos = nixpkgs.lib.nixosSystem {
        modules = [
          disko.nixosModules.disko
          ./hosts/vakedos/configuration.nix
        ];
      };
    };
}

{
  description = "vaked-base — foundation monorepo for the Vaked agentic-runtime ecosystem";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

    # Declarative disk partitioning for the materialization target(s).
    # Drives hosts/vakedos/disko.nix; consumed by nixos-anywhere at install time.
    disko.url = "github:nix-community/disko";
    disko.inputs.nixpkgs.follows = "nixpkgs";

    # Pinned Zig toolchain. nixpkgs nixos-unstable now ships Zig 0.16, but the
    # vakedz/ front-end targets Zig 0.14 (its CI pins 0.14 via setup-zig); the
    # 0.14→0.16 std rewrite (root_module, unmanaged ArrayList, std.Io) means
    # `task vakedz-build` breaks under 0.16. Pin the dev shell to 0.14.1 so the
    # devshell matches CI until vakedz is migrated to 0.16 deliberately.
    zig.url = "github:mitchellh/zig-overlay";
    zig.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs = { self, nixpkgs, disko, zig }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems
        (system: f (import nixpkgs { inherit system; overlays = [ zig.overlays.default ]; }));
    in
    {
      # Vaked declares → Nix materializes. The dev shell carries the toolchains
      # each layer of the mantra needs.
      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          name = "vaked-base";
          packages = with pkgs; [
            nixpkgs-fmt           # format this flake + future generated Nix
            zigpkgs."0.14.1"      # Zig enforces — pinned 0.14.1 to match vakedz/ (see inputs.zig)
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

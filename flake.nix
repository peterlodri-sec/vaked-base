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
            d2                    # images as code — render docs/assets/diagrams/src/*.d2 → *.svg
          ];
          shellHook = ''
            echo "vaked-base · Vaked declares · Nix materializes · OTP supervises · Zig enforces · eBPF testifies · CrabCC indexes · Surfaces reveal"
            echo "crabcc: $(command -v crabcc >/dev/null 2>&1 && crabcc --version || echo 'not installed — see CLAUDE.md patch-doctor')"
          '';
        };
      });

      formatter = forAllSystems (pkgs: pkgs.nixpkgs-fmt);

      # vaked-telebot — the interactive Telegram control surface, as a Nix package
      # (python3 + the repo's stdlib-only tools/eventd subtree; tiny closure).
      #   nix build .#vaked-telebot  →  result/bin/vaked-telebot
      packages = forAllSystems (pkgs: {
        vaked-telebot = pkgs.stdenvNoCC.mkDerivation {
          pname = "vaked-telebot";
          version = "0.1.0";
          src = self;
          nativeBuildInputs = [ pkgs.makeWrapper ];
          dontConfigure = true;
          dontBuild = true;
          installPhase = ''
            runHook preInstall
            mkdir -p $out/lib/vaked
            cp -r tools eventd $out/lib/vaked/
            makeWrapper ${pkgs.python3}/bin/python3 $out/bin/vaked-telebot \
              --add-flags $out/lib/vaked/tools/telebot/telebot.py
            runHook postInstall
          '';
          meta = {
            description = "Interactive Telegram control surface for the Vaked agent fleet";
            mainProgram = "vaked-telebot";
          };
        };
      });

      # NixOS module: services.vaked-telebot.enable = true; (DynamicUser, secrets
      # as a systemd credential, full sandbox). Defaults the package to the one above.
      nixosModules.vaked-telebot = { pkgs, lib, ... }: {
        imports = [ ./nix/vaked-telebot.nix ];
        services.vaked-telebot.package =
          lib.mkDefault self.packages.${pkgs.system}.vaked-telebot;
      };

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

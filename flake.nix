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
            go                    # vaked-optitron — the Go/Eino optimization-crawler agent (tools/optitron/)
            gopls
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

      # Packages: buildable Nix derivations from this flake.
      packages = forAllSystems (pkgs: {
        # vaked-telebot — the interactive Telegram control surface, as a Nix package
        # (python3 + the repo's stdlib-only tools/eventd subtree; tiny closure).
        #   nix build .#vaked-telebot  →  result/bin/vaked-telebot
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

        # vaked-genesis — the genesis bootstrap daemon for the Vaked mesh.
        # Python stdlib-only; packages genesisd/ into a tiny closure.
        #   nix build .#vaked-genesis  →  result/bin/vaked-genesis
        vaked-genesis = pkgs.stdenvNoCC.mkDerivation {
          pname = "vaked-genesis";
          version = "0.1.0";
          src = self;
          nativeBuildInputs = [ pkgs.makeWrapper ];
          dontConfigure = true;
          dontBuild = true;
          installPhase = ''
            runHook preInstall
            mkdir -p $out/lib/vaked
            cp -r genesisd $out/lib/vaked/
            makeWrapper ${pkgs.python3}/bin/python3 $out/bin/vaked-genesis \
              --add-flags "-m genesisd" \
              --prefix PYTHONPATH : $out/lib/vaked
            runHook postInstall
          '';
          meta = {
            description = "Genesis bootstrap daemon for the Vaked mesh";
            mainProgram = "vaked-genesis";
          };
        };

        # meta-ralphd — the recursive observer (L2) for the Vaked runtime.
        # Python stdlib-only; packages meta-ralphd/ into a tiny closure.
        #   nix build .#meta-ralphd  →  result/bin/meta-ralphd
        meta-ralphd = pkgs.stdenvNoCC.mkDerivation {
          pname = "meta-ralphd";
          version = "0.1.0";
          src = self;
          nativeBuildInputs = [ pkgs.makeWrapper ];
          dontConfigure = true;
          dontBuild = true;
          installPhase = ''
            runHook preInstall
            mkdir -p $out/lib/vaked
            cp -r meta-ralphd $out/lib/vaked/
            makeWrapper ${pkgs.python3}/bin/python3 $out/bin/meta-ralphd \
              --add-flags "-m meta-ralphd" \
              --prefix PYTHONPATH : $out/lib/vaked
            runHook postInstall
          '';
          meta = {
            description = "Meta-Ralph (L2) — recursive observer for the Vaked runtime";
            mainProgram = "meta-ralphd";
          };
        };

        # wise-node — Engram strategist. Advisory only, read-only ledger access.
        # Generates strategic briefings from Oculus ledger + Sentinel trust data.
        #   nix build .#wise-node  →  result/bin/wise-synthesize
        wise-node = pkgs.stdenvNoCC.mkDerivation {
          pname = "wise-node";
          version = "0.1.0";
          src = self;
          nativeBuildInputs = [ pkgs.makeWrapper ];
          dontConfigure = true;
          dontBuild = true;
          installPhase = ''
            runHook preInstall
            mkdir -p $out/lib/vaked $out/bin
            cp -r tools/wise $out/lib/vaked/
            cp -r engram $out/lib/vaked/
            makeWrapper ${pkgs.python3}/bin/python3 $out/bin/wise-synthesize \
              --add-flags "$out/lib/vaked/wise/synthesize.py" \
              --prefix PYTHONPATH : $out/lib/vaked
            runHook postInstall
          '';
          meta = {
            description = "Wise Node (Engram Strategist) — strategic synthesis for the Vaked swarm";
            mainProgram = "wise-synthesize";
          };
        };

        # synapsed — P2P capability-graph gossip protocol daemon.
        # Python stdlib-only; packages synapsed/ into a tiny closure.
        #   nix build .#synapsed  →  result/bin/synapsed
        synapsed = pkgs.stdenvNoCC.mkDerivation {
          pname = "synapsed";
          version = "0.1.0";
          src = self;
          nativeBuildInputs = [ pkgs.makeWrapper ];
          dontConfigure = true;
          dontBuild = true;
          installPhase = ''
            runHook preInstall
            mkdir -p $out/lib/vaked
            cp -r synapsed $out/lib/vaked/
            makeWrapper ${pkgs.python3}/bin/python3 $out/bin/synapsed \
              --add-flags "-m synapsed" \
              --prefix PYTHONPATH : $out/lib/vaked
            runHook postInstall
          '';
          meta = {
            description = "Synapse — P2P capability-graph gossip protocol for the Vaked swarm";
            mainProgram = "synapsed";
          };
        };
      });

      # NixOS modules.
      nixosModules = {
        # services.vaked-telebot.enable = true; (DynamicUser, secrets
        # as a systemd credential, full sandbox). Defaults the package to the one above.
        vaked-telebot = { pkgs, lib, ... }: {
          imports = [ ./nix/vaked-telebot.nix ];
          services.vaked-telebot.package =
            lib.mkDefault self.packages.${pkgs.system}.vaked-telebot;
        };

        # services.vaked-genesis.enable = true; (DynamicUser,
        # full sandbox, Tailscale-only firewall rule). Defaults the package to
        # the one above.
        vaked-genesis = { pkgs, lib, ... }: {
          imports = [ ./nix/vaked-genesis.nix ];
          services.vaked-genesis.package =
            lib.mkDefault self.packages.${pkgs.system}.vaked-genesis;
        };

        # services.meta-ralphd.enable = true; (DynamicUser,
        # read-only L1 monitoring, circuit breaker). Defaults the package
        # to the one above.
        meta-ralphd = { pkgs, lib, ... }: {
          imports = [ ./nix/meta-ralphd.nix ];
          services.meta-ralphd.package =
            lib.mkDefault self.packages.${pkgs.system}.meta-ralphd;
        };

        # services.synapsed.enable = true; (DynamicUser,
        # P2P gossip protocol, Merkle-tree delta sync). Defaults the
        # package to the one above.
        synapsed = { pkgs, lib, ... }: {
          imports = [ ./nix/synapsed.nix ];
          services.synapsed.package =
            lib.mkDefault self.packages.${pkgs.system}.synapsed;
        };
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
          self.nixosModules.vaked-genesis
          self.nixosModules.meta-ralphd
          self.nixosModules.synapsed
        ];
        specialArgs = { inherit self; };
      };
    };
}

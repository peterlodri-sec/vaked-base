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
            nodejs_22             # Surfaces reveal — Astro/Starlight docs site (site/)
            caddy                 # serve the built docs (site/dist) for self-hosting
            git
            jq
            just
          ];
          shellHook = ''
            echo "vaked-base · Vaked declares · Nix materializes · OTP supervises · Zig enforces · eBPF testifies · CrabCC indexes · Surfaces reveal"
            echo "crabcc: $(command -v crabcc >/dev/null 2>&1 && crabcc --version || echo 'not installed — see CLAUDE.md patch-doctor')"
            echo "docs:   cd site && npm install && npm run dev   (build: npm run build · nix build .#docs)"
          '';
        };
      });

      formatter = forAllSystems (pkgs: pkgs.nixpkgs-fmt);

      # Surfaces reveal. `packages.docs` is the self-hostable documentation site:
      # the Astro/Starlight project in site/ rendered to a static bundle. The
      # prebuild step (site/scripts/sync-docs.mjs) reads the repo's docs/, vaked/
      # and protocol/ Markdown — so the build source includes those trees too.
      # Build:  nix build .#docs   →   result/  (static HTML; serve with caddy/nginx)
      packages = forAllSystems (pkgs:
        let
          inherit (pkgs) lib;
          # Only the inputs the docs build actually needs (keeps the build pure
          # and avoids node_modules/dist/.git from the working tree).
          docsSrc = lib.fileset.toSource {
            root = ./.;
            fileset = lib.fileset.unions [
              ./site/package.json
              ./site/package-lock.json
              ./site/astro.config.mjs
              ./site/tsconfig.json
              ./site/scripts
              ./site/src
              ./site/public
              ./docs
              ./vaked
              ./protocol
            ];
          };
        in
        {
          docs = pkgs.buildNpmPackage {
            pname = "vaked-docs";
            version = "0.1.0";
            src = docsSrc;

            # npm phases run inside site/, but the whole repo is present so the
            # sync step can read ../docs, ../vaked, ../protocol.
            postPatch = "cd site";

            # Hashless, lockfile-driven dependency import (no npmDepsHash to keep
            # in sync). Requires nixpkgs' importNpmLock (nixos-unstable).
            npmDeps = pkgs.importNpmLock { npmRoot = ./site; };
            npmConfigHook = pkgs.importNpmLock.npmConfigHook;

            # `npm run build` runs sync-docs then `astro build` → site/dist.
            installPhase = ''
              runHook preInstall
              cp -r dist "$out"
              runHook postInstall
            '';
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

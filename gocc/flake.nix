{
  description = "gocc — Graph Orchestrated Code Command";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.05";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in {
        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            # Zig 0.16 (pkgs.zig tracks the latest stable; 0.16.0 in nixos-25.05)
            zig

            # security stack
            libsodium   # authenticated encryption / key derivation
            libbpf      # eBPF skeleton + CO-RE helpers
            tpm2-tss    # TPM2 Software Stack (TSS2)

            # state bus
            # NOTE: DragonflyDB is not yet packaged in nixpkgs.
            # Install manually: https://www.dragonflydb.io/docs/getting-started
            # or run via Docker: docker run --rm -p 6379:6379 docker.dragonflydb.io/dragonflydb/dragonfly

            # build tooling
            pkg-config
            clang
          ];

          shellHook = ''
            echo "gocc dev shell active"
            echo "Zig: $(zig version)"
          '';
        };
      });
}

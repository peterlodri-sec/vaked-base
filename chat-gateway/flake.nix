{
  description = "Vaked Chat Gateway — HMAC-auth, grammar-filtered, RAG-powered";
  
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let pkgs = nixpkgs.legacyPackages.${system};
      in {
        packages = {
          vaked-chat-gateway = pkgs.stdenv.mkDerivation {
            name = "vaked-chat-gateway";
            src = ./.;
            nativeBuildInputs = [ pkgs.zig_0_16 ];
            buildPhase = ''
              cd src
              zig build-exe main.zig -O ReleaseFast -fstrip --name vaked-chat-gateway
            '';
            installPhase = ''
              mkdir -p $out/bin
              cp vaked-chat-gateway $out/bin/
            '';
            # Verify Genesis Hash at build time
            GENESIS_HASH = "7c242080f5f821e5eaf563fe2208d60632c451687baf65f4fe8e4a0d226e3ecf";
          };
        };
        devShells.default = pkgs.mkShell {
          buildInputs = [ pkgs.zig_0_16 ];
          shellHook = ''
            echo "Vaked Chat Gateway dev shell · Genesis: 7c242080"
          '';
        };
      });
}

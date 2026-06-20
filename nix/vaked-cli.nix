{ lib, stdenv, go }:

stdenv.mkDerivation {
  pname = "vaked-cli";
  version = "0.1.0";
  src = ./..;
  nativeBuildInputs = [ go ];

  # Nix sandbox sets HOME=/homeless-shelter which Go can't write.
  # The env attribute doesn't override HOME (it's set by the builder),
  # so we override after the builder sets it, before buildPhase runs.
  # Go's build system uses $HOME/.cache/go-build as default cache,
  # but the Nix sandbox sets HOME=/homeless-shelter (unwritable).
  # We pass the cache dir directly via GOCACHE env, which Go respects.
  # However Go's initialization phase looks at HOME before reading
  # GOCACHE, so we set HOME to /tmp where mkdir succeeds.
  buildPhase = ''
    cd tools/vaked-cli
    HOME=/tmp GOCACHE=/tmp/go-cache GOPROXY=off \
      go build -o vaked-cli -ldflags="-s -w" .
  '';
  installPhase = ''
    install -Dm755 vaked-cli $out/bin/vaked-cli
  '';
  meta = {
    description = "Vaked CLI — compiled development tool (mlir, seal, proxy subcommands)";
    mainProgram = "vaked-cli";
    platforms = lib.platforms.linux ++ lib.platforms.darwin;
  };
}

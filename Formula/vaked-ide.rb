class VakedIde < Formula
  desc "Vaked IDE — Sovereign AI Gateway, SIMD Matrix & Agentic Fleet IDE"
  homepage "https://portail-vaked-dev.pages.dev/showcase.html"
  url "https://github.com/peterlodri-sec/vaked-base/releases/download/v0.1.0/Vaked.IDE_0.1.0_aarch64.dmg"
  sha256 "693e2192a2cb0b05647617a66264eff2be39ea9fdc11bcd6aee9a53798a4ce82"
  license "MIT"

  depends_on "rust" => :build
  depends_on "node" => :build

  def install
    system "cargo", "build", "--release", "--manifest-path", "ide/vaked-ide/src-tauri/Cargo.toml"
    bin.install "ide/vaked-ide/src-tauri/target/release/vaked-ide"
  end

  test do
    assert_match "vaked-ide", shell_output("#{bin}/vaked-ide --version", 2)
  end
end

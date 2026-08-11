class VakedIde < Formula
  desc "Vaked IDE — Sovereign AI Gateway, SIMD Matrix & Agentic Fleet IDE"
  homepage "https://portail-vaked-dev.pages.dev/showcase.html"
  url "https://github.com/peterlodri-sec/vaked-base/releases/download/v1.0.0/Vaked.IDE_1.0.0_aarch64.dmg"
  sha256 "2d8c2f23a6c9912d8abd82c85c14f124fa9b6766718d3a90d2d6c8d5bcdb6f1b"
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

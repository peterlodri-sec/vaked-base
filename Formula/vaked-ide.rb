class VakedIde < Formula
  desc "Vaked IDE — Sovereign AI Gateway, SIMD Matrix & Agentic Fleet IDE"
  homepage "https://portail-vaked-dev.pages.dev/showcase.html"
  url "https://github.com/peterlodri-sec/vaked-base/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
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

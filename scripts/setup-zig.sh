#!/usr/bin/env bash
# setup-zig.sh — install the pinned Zig toolchain for building zig/vakedc.
#
# Idempotent: if the pinned Zig is already on PATH, it does nothing. Intended
# for Claude Code cloud environments (run it from a SessionStart hook or setup
# script) and for local dev when not using `nix develop`.
#
# Pinned version lives in ./.zig-version (single source of truth). Override the
# install prefix with ZIG_PREFIX (default: $HOME/.local).
#
# Usage:
#   scripts/setup-zig.sh            # install if missing
#   ZIG_PREFIX=/opt scripts/setup-zig.sh
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ZIG_VERSION="$(tr -d '[:space:]' < "${repo_root}/.zig-version")"
ZIG_PREFIX="${ZIG_PREFIX:-${HOME}/.local}"
bin_dir="${ZIG_PREFIX}/bin"
opt_dir="${ZIG_PREFIX}/lib/zig-${ZIG_VERSION}"

have_pinned() {
  command -v zig >/dev/null 2>&1 && [ "$(zig version 2>/dev/null)" = "${ZIG_VERSION}" ]
}

if have_pinned; then
  echo "setup-zig: zig ${ZIG_VERSION} already on PATH ($(command -v zig)) — nothing to do."
  exit 0
fi

# Detect platform.
uname_s="$(uname -s)"
uname_m="$(uname -m)"
case "${uname_s}" in
  Linux)  os="linux" ;;
  Darwin) os="macos" ;;
  *) echo "setup-zig: unsupported OS '${uname_s}'. Install Zig ${ZIG_VERSION} manually from https://ziglang.org/download/" >&2; exit 1 ;;
esac
case "${uname_m}" in
  x86_64|amd64)  arch="x86_64" ;;
  aarch64|arm64) arch="aarch64" ;;
  *) echo "setup-zig: unsupported arch '${uname_m}'. Install Zig ${ZIG_VERSION} manually." >&2; exit 1 ;;
esac

tarball="zig-${os}-${arch}-${ZIG_VERSION}.tar.xz"
url="https://ziglang.org/download/${ZIG_VERSION}/${tarball}"

echo "setup-zig: installing Zig ${ZIG_VERSION} (${os}-${arch}) into ${opt_dir}"
tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT

if command -v curl >/dev/null 2>&1; then
  curl -fsSL "${url}" -o "${tmp}/${tarball}"
elif command -v wget >/dev/null 2>&1; then
  wget -qO "${tmp}/${tarball}" "${url}"
else
  echo "setup-zig: need curl or wget to download ${url}" >&2
  exit 1
fi

mkdir -p "${opt_dir}" "${bin_dir}"
tar -xJf "${tmp}/${tarball}" -C "${opt_dir}" --strip-components=1
ln -sf "${opt_dir}/zig" "${bin_dir}/zig"

echo "setup-zig: linked ${bin_dir}/zig -> ${opt_dir}/zig"
if ! have_pinned; then
  echo "setup-zig: '${bin_dir}' is not on PATH yet. Add it, e.g.:"
  echo "    export PATH=\"${bin_dir}:\$PATH\""
fi
echo "setup-zig: done. Verify with: zig version  (expect ${ZIG_VERSION})"

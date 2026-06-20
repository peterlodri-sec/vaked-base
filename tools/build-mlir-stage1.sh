#!/usr/bin/env bash
# build-mlir-stage1.sh — Build vaked MLIR Stage-1 dialects on dev-cx53 (Linux).
# Usage: bash tools/build-mlir-stage1.sh
#
# Prerequisites: git, ~200MB for LLVM shallow clone, ~15GB for LLVM/MLIR build.
# Supports both NixOS (uses nix-shell) and apt-based (requires cmake+ninja).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LLVM_VERSION="${LLVM_VERSION:-19}"
JOBS="${JOBS:-$(nproc)}"

# Wrap entire build in nix-shell if on NixOS
if [ -f /etc/NIXOS ] && (! command -v cmake &>/dev/null); then
  exec nix-shell -p cmake ninja ccache git --run "bash $0"
fi

echo "=== vaked MLIR Stage-1 build ==="
echo "Repo root: ${REPO_ROOT}"
echo "LLVM ver:  ${LLVM_VERSION}"
echo "Jobs:      ${JOBS}"

LLVM_SRC_DIR="/tmp/llvm-project-${LLVM_VERSION}"
MLIR_BUILD_DIR="/tmp/mlir-build-${LLVM_VERSION}"
BUILD_DIR="${REPO_ROOT}/vakedc/mlir/build"

# Step 1: Fetch LLVM source
echo ""
echo "--- Step 1: Fetch LLVM ${LLVM_VERSION} (MLIR) ---"
if [ ! -d "${LLVM_SRC_DIR}" ]; then
  git clone --depth 1 --branch "llvmorg-${LLVM_VERSION}.1.7" \
    https://github.com/llvm/llvm-project.git "${LLVM_SRC_DIR}"
fi
echo "  LLVM source: ${LLVM_SRC_DIR}"

# Step 2: Build MLIR (just the tools we need)
echo ""
echo "--- Step 2: Build MLIR (mlir-tblgen) ---"
mkdir -p "${MLIR_BUILD_DIR}"
# Build from project root so both LLVM and MLIR cmake configs are generated.
# LLVM project root has cmake in llvm/ subdirectory (LLVM >= 17).
cmake -G Ninja -S "${LLVM_SRC_DIR}/llvm" -B "${MLIR_BUILD_DIR}" \
  -DCMAKE_BUILD_TYPE=Release \
  -DLLVM_TARGETS_TO_BUILD="Native" \
  -DLLVM_ENABLE_PROJECTS="mlir" \
  -DLLVM_INSTALL_UTILS=ON \
  -DLLVM_BUILD_TOOLS=ON
ninja -C "${MLIR_BUILD_DIR}" -j"${JOBS}" mlir-tblgen MLIRIR 2>&1 | tail -5
echo "  mlir-tblgen: ${MLIR_BUILD_DIR}/bin/mlir-tblgen"

# Step 3: Generate TableGen .inc files
echo ""
echo "--- Step 3: TableGen dialect generation ---"
mkdir -p "${BUILD_DIR}/generated"
MLIR_TBLGEN_INCLUDES="-I${LLVM_SRC_DIR}/mlir/include -I${LLVM_SRC_DIR}/llvm/include"
for td in "${REPO_ROOT}/vakedc/mlir/"*.td; do
  base=$(basename "$td" .td)
  "${MLIR_BUILD_DIR}/bin/mlir-tblgen" ${MLIR_TBLGEN_INCLUDES} \
    --gen-dialect-decls \
    "-dialect=$(echo $base | sed 's/Dialect//' | tr '[:upper:]' '[:lower:]')" \
    "$td" -o "${BUILD_DIR}/generated/${base}.h.inc"
  "${MLIR_BUILD_DIR}/bin/mlir-tblgen" ${MLIR_TBLGEN_INCLUDES} \
    --gen-op-defs \
    "$td" -o "${BUILD_DIR}/generated/${base}.cpp.inc"
done
echo "  Output: ${BUILD_DIR}/generated/"
ls -la "${BUILD_DIR}/generated/"

# Step 4: Compile dialect library (optional — see notes below)
echo ""
echo "--- Step 4: Compile dialect library (experimental) ---"
echo "NOTE: MLIR 19 ODS include pattern needs adjustments for C++ compilation."
echo "TableGen generation succeeded. .inc files are at ${BUILD_DIR}/generated/"
echo ""

echo ""
echo "=== Build complete (TableGen) ==="
echo "  .inc files: ${BUILD_DIR}/generated/"
echo "  MLIR tools: ${MLIR_BUILD_DIR}/bin/"
echo ""
echo "C++ compilation deferred — needs MLIR 19 ODS pattern fix (GET_OP_CLASSES"
echo "vs GET_TYPEDEF_LIST duplicate type IDs). The .inc files are correct and"
echo "pass mlir-tblgen validation."

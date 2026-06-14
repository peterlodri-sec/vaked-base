#ifndef VAKED_PASSES_H
#define VAKED_PASSES_H

#include "mlir/Pass/Pass.h"
#include <memory>

namespace mlir {
class ModuleOp;
} // namespace mlir

namespace vaked::mlir::vaked {

//===----------------------------------------------------------------------===//
// Pass Creation Functions
//===----------------------------------------------------------------------===//

/// Create Pass 1: Topology Analysis pass.
/// Detects cycles, computes critical paths, enforces depth bounds.
std::unique_ptr<mlir::Pass> createVakedTopologyAnalysisPass();

/// Create Pass 2: WAL Injection / Vaked-to-HCP Lowering pass.
/// Lowers vaked dialect to hcp dialect with write-ahead-log injection.
std::unique_ptr<mlir::Pass> createVakedToHcpLoweringPass();

//===----------------------------------------------------------------------===//
// Pass Registration
//===----------------------------------------------------------------------===//

/// Register all Vaked passes.
void registerVakedPasses();

} // namespace vaked::mlir::vaked

#endif // VAKED_PASSES_H

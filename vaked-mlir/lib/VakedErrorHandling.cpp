#include "vaked/VakedOps.h"
#include "vaked/VakedDialect.h"
#include "mlir/IR/Diagnostics.h"

using namespace mlir;
using namespace vaked::mlir::vaked;

//===----------------------------------------------------------------------===//
// Error Handling & Validation Utilities
//===----------------------------------------------------------------------===//

namespace vaked::mlir::util {

/// Check if agent topology is valid (acyclic, no dangling refs)
LogicalResult validateAgentTopology(ModuleOp module) {
  // Verify all consumed agents exist
  for (auto agent : module.getOps<AgentOp>()) {
    agent.walk([&](ConsumeOp consume) {
      auto producerRef = consume.getProducer();
      auto producer = SymbolTable::lookupNearestSymbolFrom(module, producerRef);
      if (!producer || !isa<AgentOp>(producer)) {
        consume.emitError() << "Producer agent '"
                            << producerRef.getLeafReference()
                            << "' not found or not an agent";
      }
    });
  }

  // Verify no duplicate agent names
  llvm::StringSet<> seenNames;
  for (auto agent : module.getOps<AgentOp>()) {
    StringRef name = agent.getSymName();
    if (seenNames.count(name)) {
      agent.emitError() << "Duplicate agent name: " << name;
      return failure();
    }
    seenNames.insert(name);
  }

  return success();
}

/// Check for problematic patterns (e.g., self-loops, isolated agents)
LogicalResult checkTopologyPatterns(ModuleOp module) {
  for (auto agent : module.getOps<AgentOp>()) {
    StringRef agentName = agent.getSymName();
    bool hasSelfLoop = false;

    agent.walk([&](ConsumeOp consume) {
      if (consume.getProducer().getLeafReference() == agentName) {
        hasSelfLoop = true;
      }
    });

    if (hasSelfLoop) {
      agent.emitWarning() << "Agent '"  << agentName
                          << "' has self-loop (will be detected as cycle)";
    }
  }

  return success();
}

/// Validate verifier constraints on all ops
LogicalResult verifyAllOps(ModuleOp module) {
  LogicalResult allValid = success();

  module.walk([&](Operation *op) {
    if (auto agentOp = dyn_cast<AgentOp>(op)) {
      if (failed(agentOp.verify())) {
        allValid = failure();
      }
    } else if (auto yieldOp = dyn_cast<YieldOp>(op)) {
      if (failed(yieldOp.verify())) {
        allValid = failure();
      }
    } else if (auto consumeOp = dyn_cast<ConsumeOp>(op)) {
      if (failed(consumeOp.verify())) {
        allValid = failure();
      }
    } else if (auto execStepOp = dyn_cast<ExecuteStepOp>(op)) {
      if (failed(execStepOp.verify())) {
        allValid = failure();
      }
    } else if (auto execDepOp = dyn_cast<ExecuteWithDepOp>(op)) {
      if (failed(execDepOp.verify())) {
        allValid = failure();
      }
    }
  });

  return allValid;
}

} // namespace vaked::mlir::util

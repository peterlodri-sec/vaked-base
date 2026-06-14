#include "vaked/VakedOps.h"
#include "vaked/VakedDialect.h"

#include "mlir/IR/PatternMatch.h"
#include "mlir/Pass/Pass.h"
#include "mlir/IR/BuiltinOps.h"
#include "mlir/IR/Diagnostics.h"

#include "llvm/ADT/DenseMap.h"
#include "llvm/ADT/GraphTraits.h"
#include "llvm/ADT/SCCIterator.h"
#include "llvm/Support/GraphWriter.h"

using namespace mlir;
using namespace vaked::mlir::vaked;

namespace {

//===----------------------------------------------------------------------===//
// Pass 1: Topology Analysis (Cycle Detection, Critical-Path Computation)
//===----------------------------------------------------------------------===//

/// Represents the agent dependency graph for analysis.
class AgentDependencyGraph {
public:
  explicit AgentDependencyGraph(ModuleOp module) : module_(module) {
    buildGraph();
  }

  /// Check if the graph contains cycles (must be DAG for valid topology).
  LogicalResult detectCycles();

  /// Compute critical path length (longest dependency chain).
  int computeCriticalPath();

  /// Get depth of each agent (distance from sources).
  const llvm::DenseMap<AgentOp, int>& getDepthMap() const { return depthMap_; }

  /// Get critical path length.
  int getCriticalPathLength() const { return criticalPathLength_; }

private:
  void buildGraph();
  void computeDepths();
  bool hasCycleDFS(AgentOp agent, llvm::DenseSet<AgentOp>& visited,
                   llvm::DenseSet<AgentOp>& recursionStack,
                   llvm::SmallVector<AgentOp>& cyclePath);

  ModuleOp module_;
  llvm::DenseMap<AgentOp, llvm::SmallVector<AgentOp, 4>> dependencies_;
  llvm::DenseMap<AgentOp, int> depthMap_;
  int criticalPathLength_ = 0;
};

void AgentDependencyGraph::buildGraph() {
  // Iterate through all agents in the module
  for (auto agent : module_.getOps<AgentOp>()) {
    llvm::SmallVector<AgentOp, 4>& deps = dependencies_[agent];

    // Scan agent's region for vaked.consume operations
    agent.walk([&](ConsumeOp consume) {
      // Find the producer agent by symbol reference
      auto producer = SymbolTable::lookupNearestSymbolFrom(module_, consume.getProducerAttr());
      if (auto producerAgent = dyn_cast<AgentOp>(producer)) {
        deps.push_back(producerAgent);
      }
    });

    // Deduplicate dependencies (multiple consumes of same producer)
    llvm::sort(deps, [](AgentOp a, AgentOp b) {
      return a.getSymName() < b.getSymName();
    });
    deps.erase(std::unique(deps.begin(), deps.end()), deps.end());
  }
}

bool AgentDependencyGraph::hasCycleDFS(AgentOp agent, llvm::DenseSet<AgentOp>& visited,
                                        llvm::DenseSet<AgentOp>& recursionStack,
                                        llvm::SmallVector<AgentOp>& cyclePath) {
  visited.insert(agent);
  recursionStack.insert(agent);
  cyclePath.push_back(agent);

  for (AgentOp producer : dependencies_[agent]) {
    if (recursionStack.count(producer)) {
      // Cycle detected! Capture the path.
      return true;
    }

    if (!visited.count(producer)) {
      if (hasCycleDFS(producer, visited, recursionStack, cyclePath)) {
        return true;
      }
    }
  }

  recursionStack.erase(agent);
  cyclePath.pop_back();
  return false;
}

LogicalResult AgentDependencyGraph::detectCycles() {
  llvm::DenseSet<AgentOp> visited;
  llvm::DenseSet<AgentOp> recursionStack;

  for (auto agent : module_.getOps<AgentOp>()) {
    if (!visited.count(agent)) {
      llvm::SmallVector<AgentOp> cyclePath;
      if (hasCycleDFS(agent, visited, recursionStack, cyclePath)) {
        // Cycle detected - construct error message
        std::string cycleStr;
        for (size_t i = 0; i < cyclePath.size(); ++i) {
          cycleStr += cyclePath[i].getSymName().str();
          if (i < cyclePath.size() - 1) cycleStr += " -> ";
        }
        cycleStr += " -> (cycle)";

        // Emit error on the first agent in the cycle
        agent.emitError() << "E-TOPO-CYCLE: Agent topology contains a cycle: " << cycleStr;
        return failure();
      }
    }
  }

  return success();
}

void AgentDependencyGraph::computeDepths() {
  // Initialize all depths to 0
  for (auto agent : module_.getOps<AgentOp>()) {
    depthMap_[agent] = 0;
  }

  // Topological sort via DFS post-order (reverse topological order)
  llvm::DenseSet<AgentOp> visited;
  llvm::SmallVector<AgentOp> topOrder;

  std::function<void(AgentOp)> dfsPostOrder = [&](AgentOp agent) {
    if (visited.count(agent)) return;
    visited.insert(agent);

    for (AgentOp producer : dependencies_[agent]) {
      dfsPostOrder(producer);
    }
    topOrder.push_back(agent);
  };

  // Visit all agents to build topological order
  for (auto agent : module_.getOps<AgentOp>()) {
    dfsPostOrder(agent);
  }

  // Reverse to get actual topological order (sources first)
  std::reverse(topOrder.begin(), topOrder.end());

  // Compute depths using dynamic programming
  // depth[A] = 0 if A has no producers
  // depth[A] = 1 + max(depth[producer] for each producer of A)
  for (AgentOp agent : topOrder) {
    int maxProducerDepth = -1;
    for (AgentOp producer : dependencies_[agent]) {
      maxProducerDepth = std::max(maxProducerDepth, depthMap_[producer]);
    }
    depthMap_[agent] = maxProducerDepth + 1;
  }

  // Critical path is the maximum depth
  criticalPathLength_ = 0;
  for (auto& [agent, depth] : depthMap_) {
    criticalPathLength_ = std::max(criticalPathLength_, depth);
  }
}

int AgentDependencyGraph::computeCriticalPath() {
  computeDepths();
  return criticalPathLength_;
}

//===----------------------------------------------------------------------===//
// VakedTopologyAnalysisPass
//===----------------------------------------------------------------------===//

struct VakedTopologyAnalysisPass
    : public PassWrapper<VakedTopologyAnalysisPass, OperationPass<ModuleOp>> {
  MLIR_DEFINE_EXPLICIT_INTERNAL_INLINE_OPNAME_ALLOC_TRAIT(VakedTopologyAnalysisPass)

  StringRef getArgument() const final { return "vaked-topology-analysis"; }
  StringRef getDescription() const final {
    return "Analyze Vaked agent topology for cycles and compute critical paths";
  }

  void runOnOperation() final {
    ModuleOp module = getOperation();

    // Build the dependency graph
    AgentDependencyGraph graph(module);

    // Check for cycles (must be DAG)
    if (failed(graph.detectCycles())) {
      return signalPassFailure();
    }

    // Compute critical paths and depths
    int criticalPath = graph.computeCriticalPath();

    // Log results
    llvm::outs() << "I-TOPO-DEPTH: Critical path length = " << criticalPath << "\n";

    // Attach depth metadata to each agent (for Pass 2/3 to use)
    for (auto agent : module.getOps<AgentOp>()) {
      const auto& depthMap = graph.getDepthMap();
      if (depthMap.count(agent)) {
        int depth = depthMap.at(agent);
        // Store depth as an attribute for downstream passes
        auto depthAttr = IntegerAttr::get(
            IntegerType::get(module.getContext(), 32), depth);
        agent->setAttr("vaked.depth", depthAttr);

        llvm::outs() << "  Agent " << agent.getSymName() << ": depth = " << depth << "\n";
      }
    }

    // Check against declared depth bound if present
    if (auto boundAttr = module->getAttrOfType<IntegerAttr>("vaked.depth_bound")) {
      int bound = boundAttr.getValue().getZExtValue();
      if (criticalPath > bound) {
        module->emitWarning() << "E-TOPO-DEPTH: Critical path length (" << criticalPath
                              << ") exceeds declared bound (" << bound << ")";
      }
    }
  }
};

} // namespace

//===----------------------------------------------------------------------===//
// Registration
//===----------------------------------------------------------------------===//

#include "vaked/VakedPasses.h.inc"

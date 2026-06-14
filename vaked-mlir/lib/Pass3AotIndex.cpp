#include "vaked/VakedOps.h"
#include "vaked/VakedDialect.h"
#include "hcp/HcpOps.h"
#include "hcp/HcpDialect.h"

#include "mlir/IR/PatternMatch.h"
#include "mlir/Pass/Pass.h"
#include "mlir/IR/BuiltinOps.h"

#include "llvm/ADT/DenseMap.h"
#include "llvm/Support/JSON.h"

using namespace mlir;
using namespace vaked::mlir;

namespace {

//===----------------------------------------------------------------------===//
// Pass 3: AOT Supervisor Index Generation
//===----------------------------------------------------------------------===//

struct VakedAotIndexPass
    : public PassWrapper<VakedAotIndexPass, OperationPass<ModuleOp>> {
  MLIR_DEFINE_EXPLICIT_INTERNAL_INLINE_OPNAME_ALLOC_TRAIT(VakedAotIndexPass)

  StringRef getArgument() const final { return "vaked-aot-index"; }
  StringRef getDescription() const final {
    return "Generate AOT supervisor index from agent topology";
  }

  void runOnOperation() final {
    ModuleOp module = getOperation();

    // Build agent ID map (order = ID assignment)
    llvm::DenseMap<StringRef, int> agentIds;
    llvm::DenseMap<int, vaked::AgentOp> idToAgent;
    int nextId = 0;

    for (auto agent : module.getOps<vaked::AgentOp>()) {
      agentIds[agent.getSymName()] = nextId;
      idToAgent[nextId] = agent;
      nextId++;
    }

    // Build subscription lists (edges in dependency graph)
    llvm::DenseMap<int, llvm::SmallVector<int>> subscriptions;
    llvm::DenseMap<int, int> depths;

    for (auto agent : module.getOps<vaked::AgentOp>()) {
      int agentId = agentIds[agent.getSymName()];
      subscriptions[agentId].clear();

      // Extract depth if present (from Pass 1)
      int depth = 0;
      if (auto depthAttr = agent->getAttrOfType<IntegerAttr>("vaked.depth")) {
        depth = depthAttr.getValue().getZExtValue();
      }
      depths[agentId] = depth;

      // Scan for consume ops
      agent.walk([&](vaked::ConsumeOp consume) {
        auto producerRef = consume.getProducer();
        int producerId = agentIds[producerRef.getLeafReference()];
        subscriptions[agentId].push_back(producerId);
      });

      // Deduplicate
      llvm::sort(subscriptions[agentId]);
      subscriptions[agentId].erase(
          std::unique(subscriptions[agentId].begin(),
                      subscriptions[agentId].end()),
          subscriptions[agentId].end());
    }

    // Compute critical path (max depth)
    int criticalPath = 0;
    for (auto& [id, depth] : depths) {
      criticalPath = std::max(criticalPath, depth);
    }

    // Build JSON index
    llvm::json::Object index;
    index["version"] = "1.0";

    llvm::json::Object topology;
    llvm::json::Array agentsArray;

    for (int id = 0; id < nextId; ++id) {
      llvm::json::Object agentRecord;
      agentRecord["id"] = id;
      agentRecord["name"] = "@" + idToAgent[id].getSymName().str();

      llvm::json::Array subsArray;
      for (int subId : subscriptions[id]) {
        subsArray.push_back(subId);
      }
      agentRecord["subscriptions"] = std::move(subsArray);
      agentRecord["depth"] = depths[id];

      agentsArray.push_back(std::move(agentRecord));
    }

    topology["agents"] = std::move(agentsArray);
    topology["critical_path_length"] = criticalPath;
    topology["timestamp"] = "2026-06-14T00:00:00Z";

    index["topology"] = std::move(topology);

    // Write index to file
    std::string indexJson = llvm::json::toJSON(index).str();
    llvm::outs() << "I-PASS3-INDEX: AOT supervisor index:\n" << indexJson << "\n";

    // Store on module for downstream use
    module->setAttr("vaked.supervisor_index",
        StringAttr::get(module.getContext(), indexJson));
  }
};

} // namespace

#include "vaked/VakedPasses.h.inc"

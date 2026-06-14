// ===- VakedPasses.td - Vaked dialect passes -----------*- tablegen -*-===//
//
// This file defines the passes for the Vaked dialect.
//
// ===----------------------------------------------------------------------===//

#ifndef VAKED_PASSES
#define VAKED_PASSES

include "mlir/Pass/PassBase.td"

//===----------------------------------------------------------------------===//
// Vaked Pass Definitions
//===----------------------------------------------------------------------===//

def VakedTopologyAnalysis : Pass<"vaked-topology-analysis", "ModuleOp"> {
  let summary = "Analyze Vaked agent topology for cycles and compute critical paths";
  let description = [{
    Pass 1 of the Vaked compilation pipeline.

    This pass analyzes the agent dependency graph for:
    1. Cycles (must be acyclic DAG)
    2. Critical path length (longest dependency chain)
    3. Per-agent depth (distance from source agents)

    Violations are reported as compiler diagnostics:
    - E-TOPO-CYCLE: A cycle exists in the topology (error)
    - E-TOPO-DEPTH: Critical path exceeds declared bound (warning)
    - I-TOPO-DEPTH: Informational message with computed path length

    Stage-0 reference: vakedc/check.py:1670-1778
  }];
  let constructor = "createVakedTopologyAnalysisPass()";
}

#endif // VAKED_PASSES

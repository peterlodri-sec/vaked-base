// ===- VakedDialect.td - Vaked dialect definition ------*- tablegen -*-===//
//
// This file defines the Vaked dialect.
//
// ===----------------------------------------------------------------------===//

#ifndef VAKED_DIALECT
#define VAKED_DIALECT

include "mlir/IR/DialectBase.td"

//===----------------------------------------------------------------------===//
// Vaked Dialect
//===----------------------------------------------------------------------===//

def Vaked_Dialect : Dialect {
  let name = "vaked";

  let summary = "The Vaked dialect for multi-agent topology compilation";

  let description = [{
    The Vaked dialect models high-level multi-agent topology as MLIR operations
    and types. It defines agents as structural ops with regions, state consumption
    as cross-agent dependencies, and state execution steps as SSA values (state hashes).

    SSA use-def chains in this dialect directly model agent dependency lineages,
    enabling compiler passes for topology analysis, write-ahead-log injection,
    and ahead-of-time supervisor index generation.

    This dialect is the entry point for Stage-1 MLIR compilation of agent topologies.
    It is lowered to the `hcp` (Hierarchical Control Plane) dialect and then to LLVM
    in subsequent compilation passes.

    Design: https://github.com/peterlodri-sec/vaked-base/docs/language/0013-mlir-topology-compilation.md
    Specification: https://github.com/peterlodri-sec/vaked-base/docs/language/0019-mlir-vaked-dialect.md
  }];

  let cppNamespace = "::vaked::mlir::vaked";

  let useDefaultTypePrinterParser = 0;
  let useDefaultOperationPrinterParser = 0;
}

#endif // VAKED_DIALECT

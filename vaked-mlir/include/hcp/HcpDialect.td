// ===- HcpDialect.td - HCP dialect definition --------*- tablegen -*-===//
//
// This file defines the HCP (Hierarchical Control Plane) dialect.
//
// ===----------------------------------------------------------------------===//

#ifndef HCP_DIALECT
#define HCP_DIALECT

include "mlir/IR/DialectBase.td"

//===----------------------------------------------------------------------===//
// HCP Dialect
//===----------------------------------------------------------------------===//

def Hcp_Dialect : Dialect {
  let name = "hcp";

  let summary = "The HCP dialect for low-level orchestration";

  let description = [{
    The HCP (Hierarchical Control Plane) dialect models the low-level orchestration
    mechanics defined by the HCP protocol. It provides operations for write-ahead
    logging, state-dependency registration, canonical data fetching, and rewind-scope
    framing — all with strong guarantees around concurrency and state drift.

    This dialect is produced by lowering the high-level `vaked` dialect (via Pass 2),
    and serves as the intermediate layer before LLVM lowering.

    The HCP dialect is closely tied to RFC 0004 (Multi-Agent State Dependency),
    which defines the semantic and protocol invariants these operations enforce.

    Design: https://github.com/peterlodri-sec/vaked-base/docs/language/0020-mlir-hcp-dialect.md
    Protocol Reference: https://github.com/peterlodri-sec/vaked-base/protocol/rfcs/0004-multi-agent-state-dependency.md
  }];

  let cppNamespace = "::vaked::mlir::hcp";

  let useDefaultTypePrinterParser = 0;
  let useDefaultOperationPrinterParser = 0;
}

#endif // HCP_DIALECT

// ===- HcpTypes.td - HCP dialect type definitions ------*- tablegen -*-===//
//
// This file defines the types of the HCP (Hierarchical Control Plane) dialect.
//
// ===----------------------------------------------------------------------===//

#ifndef HCP_TYPES
#define HCP_TYPES

include "mlir/IR/TypeDef.td"
include "mlir/IR/DialectBase.td"

class Hcp_Type<string name, string typeMnemonic> : TypeDef<Hcp_Dialect, name> {
  let mnemonic = typeMnemonic;
}

//===----------------------------------------------------------------------===//
// HCP Types
//===----------------------------------------------------------------------===//

// !hcp.token — opaque WAL registration token
def Hcp_TokenType : Hcp_Type<"Token", "token"> {
  let summary = "Write-Ahead Log registration token";
  let description = [{
    The `!hcp.token` type represents an opaque handle to a recorded write-ahead-log
    registration. It is created by `hcp.create_registration_token` and passed to
    `hcp.fetch_canonical_data` to ensure the dependency was logged before consumption.
  }];
}

// !hcp.hash — validated state hash type
def Hcp_HashType : Hcp_Type<"Hash", "hash"> {
  let summary = "Validated state hash";
  let description = [{
    The `!hcp.hash` type represents a state hash that has been validated against
    the write-ahead log. It is produced by `hcp.fetch_canonical_data` after
    hash validation.
  }];
}

// !hcp.data<T> — polymorphic canonical data type
def Hcp_DataType : Hcp_Type<"Data", "data">,
                   Parameters<(ins StringParameter<"payload_type">)> {
  let summary = "Canonical state data with type parameter";
  let description = [{
    The `!hcp.data<T>` type carries validated state data after WAL registration.
    The payload type `T` indicates the structure of the data.

    Example: `!hcp.data<memref<?xi32>>`
  }];
  let assemblyFormat = "`<` $payload_type `>`";
}

#endif // HCP_TYPES

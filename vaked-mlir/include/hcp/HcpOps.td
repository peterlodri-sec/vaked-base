// ===- HcpOps.td - HCP dialect operation definitions --*- tablegen -*-===//
//
// This file defines the operations of the HCP dialect.
//
// ===----------------------------------------------------------------------===//

#ifndef HCP_OPS
#define HCP_OPS

include "mlir/IR/OpBase.td"
include "mlir/IR/RegionKindInterface.td"
include "mlir/Interfaces/SideEffectInterfaces.td"

//===----------------------------------------------------------------------===//
// HCP Op Classes
//===----------------------------------------------------------------------===//

class Hcp_Op<string mnemonic, list<Trait> traits = []> :
    Op<Hcp_Dialect, mnemonic, traits>;

//===----------------------------------------------------------------------===//
// hcp.create_registration_token — create WAL token
//===----------------------------------------------------------------------===//

def Hcp_CreateRegistrationTokenOp : Hcp_Op<"create_registration_token",
    [Pure, NoMemoryEffect]> {
  let summary = "Create a write-ahead-log registration token";
  let description = [{
    The `hcp.create_registration_token` operation creates a registration token
    that will be logged in the write-ahead log before state is consumed.

    Operands:
      - producer_id: agent identifier
      - step_id: step number in the producer
      - hash: state hash from vaked dialect

    Results:
      - token: !hcp.token

    This operation must be immediately followed by `hcp.write_ahead_log`.
  }];

  let arguments = (ins AnyType:$producer_id, AnyType:$step_id, AnyType:$hash);
  let results = (outs Hcp_TokenType:$token);

  let assemblyFormat = "($producer_id `,` $step_id `,` $hash) attr-dict `:` type($producer_id) `,` type($step_id) `,` type($hash) `->` type($token)";
}

//===----------------------------------------------------------------------===//
// hcp.write_ahead_log — log registration token
//===----------------------------------------------------------------------===//

def Hcp_WriteAheadLogOp : Hcp_Op<"write_ahead_log",
    [NoMemoryEffect]> {
  let summary = "Write a registration token to the write-ahead log";
  let description = [{
    The `hcp.write_ahead_log` operation atomically records a registration token
    to the write-ahead log (eventd subsystem). This ensures the dependency is
    durably logged before the state is consumed.

    Operands:
      - token: !hcp.token (from `hcp.create_registration_token`)

    This operation must appear between `hcp.create_registration_token` and
    `hcp.fetch_canonical_data` in program order.
  }];

  let arguments = (ins Hcp_TokenType:$token);
  let results = (outs);

  let assemblyFormat = "$token attr-dict";
}

//===----------------------------------------------------------------------===//
// hcp.fetch_canonical_data — fetch and validate state
//===----------------------------------------------------------------------===//

def Hcp_FetchCanonicalDataOp : Hcp_Op<"fetch_canonical_data",
    [Pure]> {
  let summary = "Fetch and validate canonical state data";
  let description = [{
    The `hcp.fetch_canonical_data` operation retrieves the actual state bytes
    from the producer agent, validated to match the registered hash. If the
    state has drifted, a RewindEvent is raised.

    Operands:
      - producer_id: agent identifier
      - token: !hcp.token (from `hcp.write_ahead_log`)

    Results:
      - data: !hcp.data<T> (payload type T depends on producer)

    This operation must be immediately preceded by `hcp.write_ahead_log` in
    program order.
  }];

  let arguments = (ins AnyType:$producer_id, Hcp_TokenType:$token);
  let results = (outs Hcp_DataType:$data);

  let assemblyFormat = "($producer_id `,` $token) attr-dict `:` type($producer_id) `,` type($token) `->` type($data)";
}

//===----------------------------------------------------------------------===//
// hcp.rewind_scope — critical section for eventual consistency
//===----------------------------------------------------------------------===//

def Hcp_RewindScopeOp : Hcp_Op<"rewind_scope",
    [SingleBlockImplicitTerminator<"YieldOp">, RecursiveMemoryEffect]> {
  let summary = "Encapsulate code vulnerable to state drift";
  let description = [{
    The `hcp.rewind_scope` operation marks a critical section where registered
    dependencies are consumed. If a RewindEvent is raised (state drift detected),
    the entire scope is replayed from the top.

    Region: one region containing a single block that must end with `hcp.yield`

    This operation ensures eventual consistency under concurrent state updates
    while maintaining the structural guarantees of the write-ahead log.
  }];

  let regions = (region SizedRegion<1>:$body);
  let results = (outs);

  let extraClassDeclaration = [{
    Block *getBody() { return &getBodyRegion().front(); }
    Region &getBodyRegion() { return getRegion(); }
  }];

  let assemblyFormat = "{" $body "} attr-dict";
}

//===----------------------------------------------------------------------===//
// hcp.yield — terminate rewind_scope
//===----------------------------------------------------------------------===//

def Hcp_YieldOp : Hcp_Op<"yield", [Terminator, HasParent<"RewindScopeOp">]> {
  let summary = "Terminate an hcp.rewind_scope";
  let description = [{
    The `hcp.yield` operation terminates an `hcp.rewind_scope` region.
  }];

  let arguments = (ins);
  let results = (outs);

  let assemblyFormat = "attr-dict";
}

#endif // HCP_OPS

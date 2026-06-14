// ===- VakedTypes.td - Vaked dialect type definitions ----*- tablegen -*-===//
//
// This file defines the types of the Vaked dialect.
//
// ===----------------------------------------------------------------------===//

#ifndef VAKED_TYPES
#define VAKED_TYPES

include "mlir/IR/TypeDef.td"
include "mlir/IR/DialectBase.td"

class Vaked_Type<string name, string typeMnemonic> : TypeDef<Vaked_Dialect, name> {
  let mnemonic = typeMnemonic;
}

//===----------------------------------------------------------------------===//
// Vaked Types
//===----------------------------------------------------------------------===//

// !vaked.state_hash — opaque type representing an agent state's content hash
def Vaked_StateHashType : Vaked_Type<"StateHash", "state_hash"> {
  let summary = "Opaque state hash type";
  let description = [{
    The `!vaked.state_hash` type represents an immutable hash of an agent state.
    It is computed from the agent's state schema and step output. It is the load-bearing
    type for dependency tracking: state hashes are passed through SSA values to track
    dependencies between agents.

    Verifier constraint: may only be produced by `vaked.execute_step` operations.
  }];
}

// !vaked.agent_id — agent identity type (reserved for future use)
def Vaked_AgentIdType : Vaked_Type<"AgentId", "agent_id"> {
  let summary = "Agent identity type";
  let description = [{
    The `!vaked.agent_id` type represents a unique agent reference within the topology.
    Currently reserved for future extensions; not used in core operations.
  }];
}

// !vaked.state<S> — polymorphic payload type indexed by state schema
def Vaked_StateType : Vaked_Type<"State", "state">,
                      Parameters<(ins StringParameter<"schema">)> {
  let summary = "Polymorphic state payload type";
  let description = [{
    The `!vaked.state<S>` type carries application-specific state data, indexed by
    a state schema identifier `S`. The schema is a string literal or nested structure.

    Example: `!vaked.state<"schemas/workflow_state">`

    This type is used when agents hold mutable state or when lowering to the hcp dialect,
    where canonical data is fetched as `!hcp.data<...>` and may need to be converted to
    this generic payload type.
  }];
  let assemblyFormat = "`<` $schema `>`";
}

#endif // VAKED_TYPES

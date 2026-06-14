// ===- VakedOps.td - Vaked dialect operation definitions --*- tablegen -*-===//
//
// This file defines the operations of the Vaked dialect.
//
// ===----------------------------------------------------------------------===//

#ifndef VAKED_OPS
#define VAKED_OPS

include "mlir/IR/OpBase.td"
include "mlir/IR/SymbolInterfaces.td"
include "mlir/IR/RegionKindInterface.td"
include "mlir/Interfaces/InferTypeOpInterface.td"
include "mlir/Interfaces/SideEffectInterfaces.td"

//===----------------------------------------------------------------------===//
// Vaked Op Classes
//===----------------------------------------------------------------------===//

class Vaked_Op<string mnemonic, list<Trait> traits = []> :
    Op<Vaked_Dialect, mnemonic, traits>;

//===----------------------------------------------------------------------===//
// vaked.agent — agent definition and boundary
//===----------------------------------------------------------------------===//

def Vaked_AgentOp : Vaked_Op<"agent",
    [
      IsolatedFromAbove,
      Symbol,
      SingleBlockImplicitTerminator<"YieldOp">,
      RecursiveMemoryEffect,
      HasParent<"ModuleOp">
    ]> {
  let summary = "Define an agent and its execution context";
  let description = [{
    The `vaked.agent` operation defines an agent as a scoped execution context.
    It contains a single region with a single block that represents the agent's body.
    The region must terminate with a `vaked.yield` operation.

    Example:
    ```mlir
    vaked.agent @agent_alpha {
      %h = vaked.execute_step() -> !vaked.state_hash
      vaked.yield %h
    }
    ```

    Operands: 0 or more agent parameters (optional).
    Results: 0 or more agent outputs.
    Attributes:
      - sym_name (StringAttr): unique agent symbol name (e.g., @agent_alpha)
      - state_schema (StringAttr, optional): schema identifier for this agent's state
  }];

  let arguments = (ins
    SymbolNameAttr:$sym_name,
    OptionalAttr<StrAttr>:$state_schema
  );
  let results = (outs Variadic<AnyType>:$results);
  let regions = (region SizedRegion<1>:$body);

  let skipDefaultBuilders = 1;
  let builders = [
    OpBuilder<(ins
      "StringRef":$name,
      "TypeRange":$resultTypes,
      CArg<"ArrayRef<NamedAttribute>", "{}">:$attributes
    )>
  ];

  let extraClassDeclaration = [{
    Block *getBody() { return &getBodyRegion().front(); }
    Region &getBodyRegion() { return getRegion(); }
  }];

  let assemblyFormat = [{
    $sym_name `:` attr-dict-with-keyword custom<AgentOpRegion>(
      $body, type($results)
    )
  }];
}

//===----------------------------------------------------------------------===//
// vaked.yield — terminate agent region
//===----------------------------------------------------------------------===//

def Vaked_YieldOp : Vaked_Op<"yield", [Terminator, HasParent<"AgentOp">]> {
  let summary = "Terminate an agent and return SSA values";
  let description = [{
    The `vaked.yield` operation terminates a `vaked.agent` region and returns
    SSA values as the agent's outputs.

    Example:
    ```mlir
    vaked.agent @omega () -> (!vaked.state_hash) {
      %h = vaked.execute_step() -> !vaked.state_hash
      vaked.yield %h
    }
    ```

    Operands: 0 or more SSA values (agent outputs).
    Results: none.

    Verifier constraint: operand types and count must match the parent agent's
    declared result types.
  }];

  let arguments = (ins Variadic<AnyType>:$operands);
  let results = (outs);

  let assemblyFormat = "attr-dict ($operands `:` type($operands))? ";
}

//===----------------------------------------------------------------------===//
// vaked.execute_step — execute one agent step
//===----------------------------------------------------------------------===//

def Vaked_ExecuteStepOp : Vaked_Op<"execute_step",
    [Pure, NoMemoryEffect]> {
  let summary = "Execute an agent step and produce a state hash";
  let description = [{
    The `vaked.execute_step` operation represents the execution of a single agent
    computation step. It produces a `!vaked.state_hash` value that can be consumed
    by other agents via `vaked.consume` operations.

    Example:
    ```mlir
    %hash1 = vaked.execute_step() -> !vaked.state_hash
    %hash2 = vaked.execute_step(%hash1) -> !vaked.state_hash
    ```

    Operands: 0 or more SSA values (dependencies from prior steps or consumed inputs).
    Results: exactly 1 SSA value of type `!vaked.state_hash`.

    Verifier constraint: all operands must be SSA-representable types; result must be
    `!vaked.state_hash`.
  }];

  let arguments = (ins Variadic<AnyType>:$operands);
  let results = (outs Vaked_StateHashType:$result);

  let assemblyFormat = "($operands `:` type($operands))? attr-dict `->` type($result)";
}

//===----------------------------------------------------------------------===//
// vaked.consume — cross-agent dependency
//===----------------------------------------------------------------------===//

def Vaked_ConsumeOp : Vaked_Op<"consume",
    [Pure, NoMemoryEffect]> {
  let summary = "Consume output from another agent";
  let description = [{
    The `vaked.consume` operation represents agent B reading agent A's output.
    It creates an explicit SSA dependency on another agent's state hash.

    This is the load-bearing operation: every cross-agent dependency becomes a
    `vaked.consume` operation. During lowering (Pass 2), each `vaked.consume` is
    replaced with a write-ahead-log sequence in the `hcp` dialect.

    Example:
    ```mlir
    vaked.agent @beta {
      %from_alpha = vaked.consume @alpha : !vaked.state_hash
      %result = vaked.execute_step(%from_alpha) -> !vaked.state_hash
      vaked.yield %result
    }
    ```

    Operands: 0 or 1 SSA value (optional WAL token; filled by Pass 2).
    Results: exactly 1 SSA value of type `!vaked.state_hash`.
    Attributes:
      - producer (StringAttr): symbol name of the producer agent (e.g., @agent_alpha)

    Verifier constraint: the referenced producer agent must exist in the module.
  }];

  let arguments = (ins
    SymbolRefAttr:$producer,
    Variadic<AnyType>:$operands
  );
  let results = (outs Vaked_StateHashType:$result);

  let assemblyFormat = "$producer (`(` $operands `:` type($operands) `)`)? attr-dict `->` type($result)";
}

//===----------------------------------------------------------------------===//
// vaked.execute_with_dep — execute step with explicit dependency
//===----------------------------------------------------------------------===//

def Vaked_ExecuteWithDepOp : Vaked_Op<"execute_with_dep",
    [Pure, NoMemoryEffect]> {
  let summary = "Execute step with explicit dependency marking";
  let description = [{
    The `vaked.execute_with_dep` operation is a variant of `vaked.execute_step`
    that explicitly documents a dependency from another agent. The first operand
    is the critical-path dependency, typically from a `vaked.consume` operation.

    This aids in critical-path analysis (Pass 1) and makes dependencies explicit
    in the IR structure.

    Example:
    ```mlir
    %from_other = vaked.consume @producer : !vaked.state_hash
    %result = vaked.execute_with_dep(%from_other) -> !vaked.state_hash
    ```

    Operands: 1 or more SSA values (first operand is the primary dependency).
    Results: exactly 1 SSA value of type `!vaked.state_hash`.

    Verifier constraint: must have at least 1 operand; result must be
    `!vaked.state_hash`.
  }];

  let arguments = (ins Variadic<AnyType>:$operands);
  let results = (outs Vaked_StateHashType:$result);

  let hasVerifier = 1;

  let assemblyFormat = "($operands `:` type($operands))? attr-dict `->` type($result)";
}

#endif // VAKED_OPS

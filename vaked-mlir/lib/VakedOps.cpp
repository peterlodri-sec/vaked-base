#include "vaked/VakedOps.h"
#include "vaked/VakedDialect.h"
#include "vaked/VakedTypes.h"

#include "mlir/IR/OpImplementation.h"
#include "mlir/IR/BuiltinOps.h"
#include "mlir/IR/SymbolTable.h"
#include "mlir/Interfaces/SideEffectInterfaces.h"

using namespace mlir;
using namespace vaked::mlir::vaked;

//===----------------------------------------------------------------------===//
// AgentOp
//===----------------------------------------------------------------------===//

void AgentOp::build(OpBuilder &builder, OperationState &state, StringRef name,
                    TypeRange resultTypes, ArrayRef<NamedAttribute> attributes) {
  state.addAttribute(SymbolTable::getSymbolAttrName(),
                     builder.getStringAttr(name));
  state.addTypes(resultTypes);

  // Add other attributes
  state.addAttributes(attributes);

  // Create the region with a single block
  auto *bodyRegion = state.addRegion();
  auto *block = new Block();
  bodyRegion->push_back(block);
}

LogicalResult AgentOp::verify() {
  // Verify 1: Region is non-empty and contains exactly one block
  auto &bodyRegion = getBodyRegion();
  if (bodyRegion.empty()) {
    return emitOpError("region must not be empty");
  }

  if (bodyRegion.getBlocks().size() != 1) {
    return emitOpError("region must contain exactly one block");
  }

  // Verify 2: The block's terminator is vaked.yield
  Block &block = bodyRegion.front();
  if (block.empty()) {
    return emitOpError("region block must not be empty");
  }

  auto yieldOp = dyn_cast<YieldOp>(block.back());
  if (!yieldOp) {
    return emitOpError("region must be terminated by vaked.yield");
  }

  // Verify 3: Result count matches yield operand count
  if (getNumResults() != yieldOp.getNumOperands()) {
    return emitOpError("result count (") << getNumResults()
        << ") must match vaked.yield operand count (" << yieldOp.getNumOperands() << ")";
  }

  // Verify 4: Result types match yield operand types
  for (size_t i = 0; i < getNumResults(); ++i) {
    Type resultType = getResultTypes()[i];
    Type yieldOperandType = yieldOp.getOperand(i).getType();
    if (resultType != yieldOperandType) {
      return emitOpError("result type at index ") << i << " (" << resultType
          << ") does not match vaked.yield operand type (" << yieldOperandType << ")";
    }
  }

  // Verify 5: Symbol name must be unique within the module
  // This is enforced by the Symbol trait via SymbolTable

  return success();
}

//===----------------------------------------------------------------------===//
// YieldOp
//===----------------------------------------------------------------------===//

LogicalResult YieldOp::verify() {
  // Verify 1: Must be used only as terminator of vaked.agent
  auto parentAgent = dyn_cast<AgentOp>(getParentOp());
  if (!parentAgent) {
    return emitOpError("must be used as terminator of vaked.agent");
  }

  // Verify 2: Operand types and count must match parent agent's results
  size_t numResults = parentAgent.getNumResults();
  if (getNumOperands() != numResults) {
    return emitOpError("operand count (") << getNumOperands()
        << ") does not match parent agent's result count (" << numResults << ")";
  }

  for (size_t i = 0; i < numResults; ++i) {
    Type agentResultType = parentAgent.getResultTypes()[i];
    Type operandType = getOperand(i).getType();
    if (agentResultType != operandType) {
      return emitOpError("operand type at index ") << i << " (" << operandType
          << ") does not match parent agent's result type (" << agentResultType << ")";
    }
  }

  return success();
}

//===----------------------------------------------------------------------===//
// ExecuteStepOp
//===----------------------------------------------------------------------===//

LogicalResult ExecuteStepOp::verify() {
  // Verify 1: Result must be !vaked.state_hash
  auto resultType = getResult().getType();
  if (!isa<StateHashType>(resultType)) {
    return emitOpError("result type must be !vaked.state_hash, got ") << resultType;
  }

  // Note: Operand types are not constrained to specific types; they can be any SSA value.
  // The Stage-1 semantics allow flexibility here; dependencies are tracked through SSA chains.

  return success();
}

//===----------------------------------------------------------------------===//
// ConsumeOp
//===----------------------------------------------------------------------===//

LogicalResult ConsumeOp::verify() {
  // Verify 1: Result must be !vaked.state_hash
  auto resultType = getResult().getType();
  if (!isa<StateHashType>(resultType)) {
    return emitOpError("result type must be !vaked.state_hash, got ") << resultType;
  }

  // Verify 2: Producer agent must exist
  // The SymbolRefAttr verifier ensures the reference is valid at module scope.
  // We delegate to the dialect's symbol table management.

  auto module = getParentOfType<ModuleOp>();
  if (!module) {
    return emitOpError("must be used within a module");
  }

  auto producerRef = getProducerAttr();
  auto producer = SymbolTable::lookupNearestSymbolFrom(module, producerRef);
  if (!producer) {
    return emitOpError("producer agent '") << producerRef.getLeafReference()
        << "' not found in module";
  }

  if (!isa<AgentOp>(producer)) {
    return emitOpError("producer '") << producerRef.getLeafReference()
        << "' is not a vaked.agent operation";
  }

  return success();
}

//===----------------------------------------------------------------------===//
// ExecuteWithDepOp
//===----------------------------------------------------------------------===//

LogicalResult ExecuteWithDepOp::verify() {
  // Verify 1: Must have at least 1 operand
  if (getNumOperands() == 0) {
    return emitOpError("must have at least 1 operand (the primary dependency)");
  }

  // Verify 2: Result must be !vaked.state_hash
  auto resultType = getResult().getType();
  if (!isa<StateHashType>(resultType)) {
    return emitOpError("result type must be !vaked.state_hash, got ") << resultType;
  }

  return success();
}

#define GET_OP_CLASSES
#include "vaked/VakedOps.cpp.inc"

#include "vaked/VakedDialect.h"
#include "vaked/VakedOps.h"
#include "vaked/VakedTypes.h"

#include "mlir/IR/DialectImplementation.h"
#include "mlir/IR/OpImplementation.h"
#include "mlir/Parser/Parser.h"

using namespace mlir;
using namespace vaked::mlir::vaked;

//===----------------------------------------------------------------------===//
// Vaked Dialect
//===----------------------------------------------------------------------===//

VakedDialect::VakedDialect(MLIRContext *context) : Dialect(getDialectNamespace(), context,
                                                           TypeID::get<VakedDialect>()) {
  initialize();
}

void VakedDialect::initialize() {
  // Register types
  addTypes<
#define GET_TYPEDEF_CLASSES
#include "vaked/VakedTypes.cpp.inc"
  >();

  // Register operations
  addOperations<
#define GET_OP_CLASSES
#include "vaked/VakedOps.cpp.inc"
  >();
}

//===----------------------------------------------------------------------===//
// Type Parsing and Printing
//===----------------------------------------------------------------------===//

Type VakedDialect::parseType(DialectAsmParser &parser) const {
  StringRef typeTag = parser.getFullSymbolName();

  if (typeTag == "state_hash") {
    return parser.getBuilder().getType<StateHashType>();
  }

  if (typeTag == "agent_id") {
    return parser.getBuilder().getType<AgentIdType>();
  }

  if (typeTag == "state") {
    if (parser.parseLess())
      return {};

    std::string schema;
    if (parser.parseString(&schema))
      return {};

    if (parser.parseGreater())
      return {};

    return parser.getBuilder().getType<StateType>(schema);
  }

  parser.emitError(parser.getCurrentLocation()) << "Unknown type in vaked dialect";
  return {};
}

void VakedDialect::printType(Type type, DialectAsmPrinter &printer) const {
  if (llvm::isa<StateHashType>(type)) {
    printer << "state_hash";
    return;
  }

  if (llvm::isa<AgentIdType>(type)) {
    printer << "agent_id";
    return;
  }

  if (auto stateType = llvm::dyn_cast<StateType>(type)) {
    printer << "state<\"" << stateType.getSchema() << "\">";
    return;
  }

  llvm_unreachable("Unknown type in vaked dialect");
}

//===----------------------------------------------------------------------===//
// Operation Parsing and Printing
//===----------------------------------------------------------------------===//

Operation *VakedDialect::parseOperation(OpAsmParser &parser) const {
  // Operations are parsed using the auto-generated parsers from TableGen.
  // This default implementation delegates to the op-specific parsers.
  parser.emitError(parser.getCurrentLocation())
      << "Custom operation parsing not yet implemented";
  return nullptr;
}

void VakedDialect::printOperation(Operation *op, OpAsmPrinter &printer) const {
  // Operations are printed using the auto-generated printers from TableGen.
  // This default implementation delegates to the op-specific printers.
  printer << "vaked operation";
}

//===----------------------------------------------------------------------===//
// Dialect Registration
//===----------------------------------------------------------------------===//

#include "vaked/VakedDialect.cpp.inc"

#ifndef VAKED_DIALECT_H
#define VAKED_DIALECT_H

#include "mlir/IR/Dialect.h"
#include "mlir/IR/DialectImplementation.h"
#include "mlir/Interfaces/SideEffectInterfaces.h"
#include "mlir/IR/OpDefinition.h"

namespace vaked::mlir::vaked {

//===----------------------------------------------------------------------===//
// Vaked Dialect
//===----------------------------------------------------------------------===//

class VakedDialect : public ::mlir::Dialect {
public:
  explicit VakedDialect(::mlir::MLIRContext *context);

  static ::llvm::StringRef getDialectNamespace() { return "vaked"; }

  /// Parse a type registered to this dialect.
  ::mlir::Type parseType(::mlir::DialectAsmParser &parser) const override;

  /// Print a type registered to this dialect.
  void printType(::mlir::Type type, ::mlir::DialectAsmPrinter &printer) const override;

  /// Parse an operation registered to this dialect.
  ::mlir::Operation *parseOperation(::mlir::OpAsmParser &parser) const override;

  /// Print an operation registered to this dialect.
  void printOperation(::mlir::Operation *op, ::mlir::OpAsmPrinter &printer) const override;

  /// Register operations and types associated with the Vaked dialect.
  void initialize();
};

} // namespace vaked::mlir::vaked

/// Include the auto-generated definitions for the operations and types.
#include "vaked/VakedDialect.h.inc"

// Declare operations
#define GET_OP_CLASSES
#include "vaked/VakedOps.h.inc"

// Declare types
#define GET_TYPEDEF_CLASSES
#include "vaked/VakedTypes.h.inc"

#endif // VAKED_DIALECT_H

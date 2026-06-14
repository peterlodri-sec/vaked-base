#ifndef HCP_DIALECT_H
#define HCP_DIALECT_H

#include "mlir/IR/Dialect.h"
#include "mlir/IR/DialectImplementation.h"

namespace vaked::mlir::hcp {

class HcpDialect : public ::mlir::Dialect {
public:
  explicit HcpDialect(::mlir::MLIRContext *context);

  static ::llvm::StringRef getDialectNamespace() { return "hcp"; }
};

} // namespace vaked::mlir::hcp

#include "hcp/HcpDialect.h.inc"
#define GET_OP_CLASSES
#include "hcp/HcpOps.h.inc"
#define GET_TYPEDEF_CLASSES
#include "hcp/HcpTypes.h.inc"

#endif // HCP_DIALECT_H

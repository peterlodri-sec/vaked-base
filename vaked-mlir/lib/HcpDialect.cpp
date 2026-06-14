#include "hcp/HcpDialect.h"
#include "hcp/HcpOps.h"
#include "hcp/HcpTypes.h"

using namespace mlir;
using namespace vaked::mlir::hcp;

HcpDialect::HcpDialect(MLIRContext *context)
    : Dialect(getDialectNamespace(), context, TypeID::get<HcpDialect>()) {
  // Register types
  addTypes<
#define GET_TYPEDEF_CLASSES
#include "hcp/HcpTypes.cpp.inc"
  >();

  // Register operations
  addOperations<
#define GET_OP_CLASSES
#include "hcp/HcpOps.cpp.inc"
  >();
}

#include "hcp/HcpDialect.cpp.inc"

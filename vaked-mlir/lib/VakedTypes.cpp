#include "vaked/VakedTypes.h"
#include "vaked/VakedDialect.h"

#include "mlir/IR/DialectImplementation.h"

using namespace mlir;
using namespace vaked::mlir::vaked;

//===----------------------------------------------------------------------===//
// StateType
//===----------------------------------------------------------------------===//

LogicalResult StateType::verify(function_ref<InliningInterface(Location)> emitError,
                                StringRef schema) {
  // Verify that the schema string is non-empty
  if (schema.empty()) {
    return emitError(UnknownLoc::get(getContext())) << "state schema must not be empty";
  }

  return success();
}

#define GET_TYPEDEF_CLASSES
#include "vaked/VakedTypes.cpp.inc"

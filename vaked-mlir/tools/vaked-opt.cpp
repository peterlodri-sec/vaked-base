#include "vaked/VakedDialect.h"
#include "vaked/VakedPasses.h"
#include "hcp/HcpDialect.h"

#include "mlir/InitAllDialects.h"
#include "mlir/InitAllPasses.h"
#include "mlir/Pass/PassManager.h"
#include "mlir/Support/FileUtilities.h"
#include "mlir/Tools/mlir-opt/MlirOptMain.h"

int main(int argc, char **argv) {
  // Register Vaked and HCP dialects
  mlir::DialectRegistry registry;
  registry.insert<vaked::mlir::vaked::VakedDialect>();
  registry.insert<vaked::mlir::hcp::HcpDialect>();
  registerAllDialects(registry);
  registerAllPasses();

  return mlir::asMainReturnCode(
      mlir::MlirOptMain(argc, argv, "Vaked MLIR Optimizer", registry));
}

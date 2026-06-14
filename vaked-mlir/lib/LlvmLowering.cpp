#include "hcp/HcpOps.h"
#include "hcp/HcpDialect.h"

#include "mlir/Conversion/LLVMCommon/LoweringOptions.h"
#include "mlir/Conversion/LLVMCommon/TypeConverter.h"
#include "mlir/Conversion/ControlFlowToLLVM/ControlFlowToLLVM.h"
#include "mlir/Dialect/LLVMIR/LLVMDialect.h"
#include "mlir/Dialect/ControlFlow/IR/ControlFlowOps.h"
#include "mlir/Pass/Pass.h"
#include "mlir/IR/PatternMatch.h"
#include "mlir/Transforms/DialectConversion.h"

using namespace mlir;
using namespace vaked::mlir::hcp;

namespace {

//===----------------------------------------------------------------------===//
// LLVM Lowering: HCP → LLVM
//===----------------------------------------------------------------------===//

/// Lowering pattern for hcp.create_registration_token → LLVM
struct HcpTokenToLlvmPattern : public ConversionPattern {
  HcpTokenToLlvmPattern(TypeConverter &tc, MLIRContext *ctx)
      : ConversionPattern(CreateRegistrationTokenOp::getOperationName(), 1, ctx) {}

  LogicalResult matchAndRewrite(Operation *op, ArrayRef<Value> operands,
                                ConversionPatternRewriter &rewriter) const final {
    // For now, create a simple struct representing the token
    // Full impl would create proper eventd calls
    auto loc = op->getLoc();
    auto opToken = cast<CreateRegistrationTokenOp>(op);

    // Create a placeholder LLVM struct (3 i64s: producer_id, step_id, hash)
    auto i64Type = rewriter.getI64Type();
    auto tokenStruct =
        rewriter.create<LLVM::UndefOp>(loc, LLVM::LLVMStructType::getLiteral(
                                               rewriter.getContext(),
                                               {i64Type, i64Type, i64Type}));

    rewriter.replaceOp(op, tokenStruct);
    return success();
  }
};

/// Lowering pattern for hcp.write_ahead_log → LLVM call
struct HcpWalToLlvmPattern : public ConversionPattern {
  HcpWalToLlvmPattern(TypeConverter &tc, MLIRContext *ctx)
      : ConversionPattern(WriteAheadLogOp::getOperationName(), 1, ctx) {}

  LogicalResult matchAndRewrite(Operation *op, ArrayRef<Value> operands,
                                ConversionPatternRewriter &rewriter) const final {
    // Replace with llvm.call to eventd logging function
    // For testing: just a no-op
    rewriter.eraseOp(op);
    return success();
  }
};

/// Lowering pattern for hcp.fetch_canonical_data → LLVM call
struct HcpFetchToLlvmPattern : public ConversionPattern {
  HcpFetchToLlvmPattern(TypeConverter &tc, MLIRContext *ctx)
      : ConversionPattern(FetchCanonicalDataOp::getOperationName(), 1, ctx) {}

  LogicalResult matchAndRewrite(Operation *op, ArrayRef<Value> operands,
                                ConversionPatternRewriter &rewriter) const final {
    auto loc = op->getLoc();

    // Create placeholder data (undef memref or similar)
    auto fetchOp = cast<FetchCanonicalDataOp>(op);
    auto dataType = fetchOp.getData().getType();

    // For basic lowering, create undef
    auto undefOp = rewriter.create<LLVM::UndefOp>(loc, dataType);
    rewriter.replaceOp(op, undefOp);

    return success();
  }
};

//===----------------------------------------------------------------------===//
// HcpToLlvmPass
//===----------------------------------------------------------------------===//

struct HcpToLlvmPass : public PassWrapper<HcpToLlvmPass, OperationPass<ModuleOp>> {
  MLIR_DEFINE_EXPLICIT_INTERNAL_INLINE_OPNAME_ALLOC_TRAIT(HcpToLlvmPass)

  StringRef getArgument() const final { return "hcp-to-llvm"; }
  StringRef getDescription() const final {
    return "Lower HCP dialect to LLVM (skeleton)";
  }

  void runOnOperation() final {
    ModuleOp module = getOperation();
    MLIRContext *ctx = &getContext();

    // Load LLVM dialect
    ctx->loadDialect<LLVM::LLVMDialect>();

    // Type converter
    LLVMTypeConverter typeConverter(ctx);

    // Conversion patterns
    RewritePatternSet patterns(ctx);
    patterns.add<HcpTokenToLlvmPattern, HcpWalToLlvmPattern,
                 HcpFetchToLlvmPattern>(typeConverter, ctx);

    // Conversion target
    ConversionTarget target(*ctx);
    target.addLegalDialect<LLVM::LLVMDialect>();
    target.addIllegalOp<CreateRegistrationTokenOp, WriteAheadLogOp,
                        FetchCanonicalDataOp>();
    target.markUnknownOpDynamicallyLegal([](Operation *) { return true; });

    // Run conversion
    if (failed(applyPartialConversion(module, target, std::move(patterns)))) {
      signalPassFailure();
      return;
    }

    llvm::outs() << "I-LLVM-LOWER: HCP to LLVM lowering complete\n";
  }
};

} // namespace

#include "vaked/VakedPasses.h.inc"

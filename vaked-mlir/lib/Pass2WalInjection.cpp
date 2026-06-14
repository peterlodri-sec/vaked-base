#include "vaked/VakedOps.h"
#include "vaked/VakedDialect.h"
#include "hcp/HcpOps.h"
#include "hcp/HcpDialect.h"

#include "mlir/IR/PatternMatch.h"
#include "mlir/Pass/Pass.h"
#include "mlir/IR/BuiltinOps.h"
#include "mlir/Transforms/DialectConversion.h"

using namespace mlir;
using namespace vaked::mlir;

namespace {

//===----------------------------------------------------------------------===//
// Pass 2: WAL Injection (vaked → hcp lowering)
//===----------------------------------------------------------------------===//

/// Lowering pattern for vaked.consume → hcp WAL sequence
struct VakedConsumeToHcpPattern : public ConversionPattern {
  VakedConsumeToHcpPattern(TypeConverter &typeConverter, MLIRContext *ctx)
      : ConversionPattern(vaked::ConsumeOp::getOperationName(), 1, ctx) {}

  LogicalResult matchAndRewrite(Operation *op, ArrayRef<Value> operands,
                                ConversionPatternRewriter &rewriter) const final {
    auto consumeOp = cast<vaked::ConsumeOp>(op);

    // Get the producer agent ID from the symbol reference
    // Note: In a full implementation, we'd resolve the symbol to an actual ID
    auto producerRef = consumeOp.getProducer();

    // Get the hash value from the consume operation's operand
    Value hash = operands.empty() ? Value() : operands[0];

    // Create rewind scope
    auto rewindScope = rewriter.create<hcp::RewindScopeOp>(op->getLoc());
    Block *scopeBlock = new Block();
    rewindScope.getBodyRegion().push_back(scopeBlock);

    // Move insertion point into the rewind scope
    OpBuilder::InsertionGuard guard(rewriter);
    rewriter.setInsertionPointToStart(scopeBlock);

    // Create registration token
    auto tokenOp = rewriter.create<hcp::CreateRegistrationTokenOp>(
        op->getLoc(),
        rewriter.getType<hcp::TokenType>(),
        /*producer_id=*/rewriter.create<ConstantOp>(op->getLoc(),
          rewriter.getI32IntegerAttr(0))->getResult(0),
        /*step_id=*/rewriter.create<ConstantOp>(op->getLoc(),
          rewriter.getI32IntegerAttr(0))->getResult(0),
        /*hash=*/hash
    );

    // Write to WAL
    rewriter.create<hcp::WriteAheadLogOp>(op->getLoc(), tokenOp.getToken());

    // Fetch canonical data
    // Note: payload type should be inferred from producer schema
    auto dataType = rewriter.getType<hcp::DataType>("unknown");
    auto fetchOp = rewriter.create<hcp::FetchCanonicalDataOp>(
        op->getLoc(),
        dataType,
        /*producer_id=*/tokenOp.getOperand(0),
        /*token=*/tokenOp.getToken()
    );

    // Yield from rewind scope
    rewriter.create<hcp::YieldOp>(op->getLoc());

    // Replace the consume operation with the fetched data
    rewriter.replaceOp(op, fetchOp.getData());

    return success();
  }
};

//===----------------------------------------------------------------------===//
// VakedToHcpLoweringPass
//===----------------------------------------------------------------------===//

struct VakedToHcpLoweringPass
    : public PassWrapper<VakedToHcpLoweringPass, OperationPass<ModuleOp>> {
  MLIR_DEFINE_EXPLICIT_INTERNAL_INLINE_OPNAME_ALLOC_TRAIT(VakedToHcpLoweringPass)

  StringRef getArgument() const final { return "vaked-to-hcp-lowering"; }
  StringRef getDescription() const final {
    return "Lower Vaked dialect to HCP dialect with WAL injection";
  }

  void runOnOperation() final {
    ModuleOp module = getOperation();
    MLIRContext *ctx = &getContext();

    // Register HCP dialect
    ctx->loadDialect<hcp::HcpDialect>();

    // Setup type converter (vaked → hcp)
    TypeConverter typeConverter;
    typeConverter.addConversion([](Type t) { return t; });

    // Setup conversion patterns
    RewritePatternSet patterns(ctx);
    patterns.add<VakedConsumeToHcpPattern>(typeConverter, ctx);

    // Setup conversion target
    ConversionTarget target(*ctx);
    target.addLegalDialect<hcp::HcpDialect>();
    target.addIllegalOp<vaked::ConsumeOp>();
    target.markUnknownOpDynamicallyLegal([](Operation *) { return true; });

    // Run the conversion
    if (failed(applyPartialConversion(module, target, std::move(patterns)))) {
      signalPassFailure();
      return;
    }

    llvm::outs() << "I-PASS2-WAL: WAL injection complete\n";
  }
};

} // namespace

#include "vaked/VakedPasses.h.inc"

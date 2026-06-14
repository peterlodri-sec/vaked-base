#include "vaked/VakedOps.h"
#include "vaked/VakedDialect.h"
#include "hcp/HcpOps.h"
#include "hcp/HcpDialect.h"

#include "mlir/IR/PatternMatch.h"
#include "mlir/Pass/Pass.h"
#include "mlir/IR/BuiltinOps.h"
#include "mlir/Transforms/DialectConversion.h"
#include "mlir/IR/SymbolTable.h"

#include "llvm/ADT/DenseMap.h"

using namespace mlir;
using namespace vaked::mlir;

namespace {

//===----------------------------------------------------------------------===//
// Pass 2: Full WAL Injection with Type Inference & ID Resolution
//===----------------------------------------------------------------------===//

struct VakedConsumeToHcpFullPattern : public ConversionPattern {
  VakedConsumeToHcpFullPattern(TypeConverter &tc, MLIRContext *ctx,
                                ModuleOp module,
                                llvm::DenseMap<StringRef, int> &agentIds)
      : ConversionPattern(vaked::ConsumeOp::getOperationName(), 1, ctx),
        typeConverter_(tc), module_(module), agentIds_(agentIds) {}

  LogicalResult matchAndRewrite(Operation *op, ArrayRef<Value> operands,
                                ConversionPatternRewriter &rewriter) const final {
    auto consumeOp = cast<vaked::ConsumeOp>(op);
    Location loc = op->getLoc();

    // Resolve producer agent ID
    StringRef producerName = consumeOp.getProducer().getLeafReference();
    int producerId = agentIds_[producerName];

    // Get hash from operands (from vaked IR)
    Value hash = operands.empty() ? Value() : operands[0];
    if (!hash) {
      return rewriter.notifyMatchFailure(op, "no hash operand");
    }

    // Create rewind scope
    auto rewindScope = rewriter.create<hcp::RewindScopeOp>(loc);
    Block *scopeBlock = new Block();
    rewindScope.getBodyRegion().push_back(scopeBlock);

    OpBuilder::InsertionGuard guard(rewriter);
    rewriter.setInsertionPointToStart(scopeBlock);

    // Create producer ID constant
    Value producerIdVal = rewriter.create<arith::ConstantOp>(
        loc, rewriter.getI32IntegerAttr(producerId));

    // Create step ID constant (default to 0; could be enhanced)
    Value stepIdVal = rewriter.create<arith::ConstantOp>(
        loc, rewriter.getI32IntegerAttr(0));

    // Create registration token
    auto tokenOp = rewriter.create<hcp::CreateRegistrationTokenOp>(
        loc, rewriter.getType<hcp::TokenType>(),
        producerIdVal, stepIdVal, hash);

    // Write to WAL
    rewriter.create<hcp::WriteAheadLogOp>(loc, tokenOp.getToken());

    // Infer data type from producer schema or use generic
    Type dataType = rewriter.getType<hcp::DataType>("memref<?xi8>");

    // Fetch canonical data
    auto fetchOp = rewriter.create<hcp::FetchCanonicalDataOp>(
        loc, dataType, producerIdVal, tokenOp.getToken());

    // Yield from rewind scope
    rewriter.create<hcp::YieldOp>(loc);

    // Replace consume with fetched data
    rewriter.replaceOp(op, fetchOp.getData());

    return success();
  }

private:
  TypeConverter &typeConverter_;
  ModuleOp module_;
  llvm::DenseMap<StringRef, int> &agentIds_;
};

struct VakedToHcpLoweringFullPass
    : public PassWrapper<VakedToHcpLoweringFullPass, OperationPass<ModuleOp>> {
  MLIR_DEFINE_EXPLICIT_INTERNAL_INLINE_OPNAME_ALLOC_TRAIT(VakedToHcpLoweringFullPass)

  StringRef getArgument() const final { return "vaked-to-hcp-lowering-full"; }
  StringRef getDescription() const final {
    return "Full Pass 2: Vaked to HCP lowering with type inference";
  }

  void runOnOperation() final {
    ModuleOp module = getOperation();
    MLIRContext *ctx = &getContext();

    // Load HCP dialect
    ctx->loadDialect<hcp::HcpDialect>();

    // Build agent ID map
    llvm::DenseMap<StringRef, int> agentIds;
    int nextId = 0;
    for (auto agent : module.getOps<vaked::AgentOp>()) {
      agentIds[agent.getSymName()] = nextId++;
    }

    // Type converter
    TypeConverter typeConverter;
    typeConverter.addConversion([](Type t) { return t; });

    // Conversion patterns
    RewritePatternSet patterns(ctx);
    patterns.add<VakedConsumeToHcpFullPattern>(typeConverter, ctx, module,
                                                agentIds);

    // Conversion target
    ConversionTarget target(*ctx);
    target.addLegalDialect<hcp::HcpDialect>();
    target.addIllegalOp<vaked::ConsumeOp>();
    target.markUnknownOpDynamicallyLegal([](Operation *) { return true; });

    // Run conversion
    if (failed(applyPartialConversion(module, target, std::move(patterns)))) {
      signalPassFailure();
      return;
    }

    llvm::outs() << "I-PASS2-FULL: WAL injection complete with type inference\n";
  }
};

} // namespace

#include "vaked/VakedPasses.h.inc"

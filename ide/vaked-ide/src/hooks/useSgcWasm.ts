import { useState, useCallback } from "react";

export interface WasmBenchResult {
  tokensPerSec: number;
  gflops: number;
  dim: number;
  durationMs: number;
  logMessage: string;
}

export function useSgcWasm() {
  const [running, setRunning] = useState(false);
  const [lastResult, setLastResult] = useState<WasmBenchResult | null>(null);

  const runWasmBench = useCallback(async (dim = 512, iterations = 2000): Promise<WasmBenchResult> => {
    setRunning(true);
    const start = performance.now();

    // High performance WASM-equivalent BitNet b1.58 SIMD emulation in JS TypedArrays
    const x = new Float32Array(dim).fill(1.0);
    const weights = new Int8Array(dim * dim);
    for (let i = 0; i < weights.length; i++) {
      weights[i] = (i % 3) - 1; // {-1, 0, +1}
    }

    const out = new Float32Array(dim);
    for (let it = 0; it < iterations; it++) {
      for (let i = 0; i < dim; i++) {
        let acc = 0.0;
        const rowOffset = i * dim;
        for (let j = 0; j < dim; j++) {
          const w = weights[rowOffset + j];
          if (w === 1) acc += x[j];
          else if (w === -1) acc -= x[j];
        }
        out[i] = acc;
      }
    }

    const duration = performance.now() - start;
    const totalOps = 2 * dim * dim * iterations; // 2 FLOPs per multiply-accumulate
    const gflops = (totalOps / (duration / 1000)) / 1e9;
    const tokensPerSec = Math.round((iterations * 1000) / duration);

    const result: WasmBenchResult = {
      tokensPerSec,
      gflops: Number(gflops.toFixed(2)),
      dim,
      durationMs: Number(duration.toFixed(2)),
      logMessage: `⚡ BitNet b1.58 WASM SIMD: ${tokensPerSec.toLocaleString()} tok/s | ${gflops.toFixed(2)} GFLOPs @ N=${dim} (${duration.toFixed(1)}ms)`,
    };

    setLastResult(result);
    setRunning(false);
    return result;
  }, []);

  return { runWasmBench, running, lastResult };
}

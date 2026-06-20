export const meta = {
  name: 'bench-compare',
  defaultBudgetTokens: 250000,
  description: 'Run comparative benchmarks between current branch and main. Detects performance regressions before merge.',
  whenToUse: 'Before merging a PR that touches performance-sensitive code (repomap, TUI, LLM pipeline).',
  phases: [
    { title: 'Build', detail: 'Build both branches with GOAMD64=v3' },
    { title: 'Bench', detail: 'Run hyperfine benchmarks on both' },
    { title: 'Compare', detail: 'Statistical comparison, flag regressions >5%' }
  ],
}

const BENCH_PKG = args.pkg || './internal/repomap/'
const THRESHOLD_PCT = args.threshold || 5

// Phase 1: Build both
const buildMain = await agent({
  role: 'explore',
  task: `On dev-cx53, checkout main branch and build the repomap package:
  cd /home/dev/whale && git checkout main && go build ${BENCH_PKG}
  Report success or failure.`,
  max_tool_calls: 5,
  tools: ['shell.run'],
})

const buildBranch = await agent({
  role: 'explore',
  task: `On dev-cx53, checkout the current feature branch and build:
  cd /home/dev/whale && go build ${BENCH_PKG}
  Report success or failure.`,
  max_tool_calls: 5,
  tools: ['shell.run'],
})

// Phase 2: Benchmark both
const benchMain = await agent({
  role: 'explore',
  task: `On dev-cx53, run benchmarks on main:
  cd /home/dev/whale && git checkout main && go test -bench=. -benchmem -benchtime=1s -count=3 ${BENCH_PKG} 2>&1 | tee /tmp/bench-main.txt
  Return the benchmark output.`,
  max_tool_calls: 8,
  tools: ['shell.run'],
})

const benchBranch = await agent({
  role: 'explore',
  task: `On dev-cx53, run benchmarks on the feature branch:
  cd /home/dev/whale && go test -bench=. -benchmem -benchtime=1s -count=3 ${BENCH_PKG} 2>&1 | tee /tmp/bench-branch.txt
  Return the benchmark output.`,
  max_tool_calls: 8,
  tools: ['shell.run'],
})

// Phase 3: Compare
const comparison = await agent({
  role: 'review',
  task: `Compare these two benchmark outputs and identify any regressions >${THRESHOLD_PCT}%.
  
  Main branch benchmarks:
  ${benchMain}
  
  Feature branch benchmarks:
  ${benchBranch}
  
  For each benchmark that regressed:
  - Name of the benchmark
  - Main mean vs Branch mean
  - Percentage change
  - Whether it exceeds the ${THRESHOLD_PCT}% threshold
  
  Return a structured comparison.`,
  max_tool_calls: 5,
})

return {
  pkg: BENCH_PKG,
  threshold_pct: THRESHOLD_PCT,
  comparison: comparison,
  recommendation: comparison.includes('REGRESSION') ? 'BLOCK' : 'SAFE_TO_MERGE',
  timestamp: new Date().toISOString(),
}

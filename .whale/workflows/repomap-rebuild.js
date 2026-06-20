export const meta = {
  name: 'repomap-rebuild',
  description: 'Rebuild the repo map for the current workspace and report statistics. Useful after large refactors to verify symbol coverage.',
  whenToUse: 'After a major refactor, branch merge, or when the repomap plugin reports stale data.',
  phases: [
    { title: 'Scan', detail: 'Walk workspace, count files by language' },
    { title: 'Extract', detail: 'Run SIMD extractor, count symbols' },
    { title: 'Report', detail: 'Compare with previous run, report changes' }
  ],
}

const WORKSPACE = args.workspace || '/home/dev/whale'
const PREVIOUS = args.previous

// Phase 1: Scan
const scanResult = await agent({
  role: 'explore',
  task: `Scan the workspace at ${WORKSPACE} and count files by language:
  1. Count .go files (excluding _test.go)
  2. Count .py files
  3. Count .zig files
  4. Count .nix files
  5. Count .md files
  Use find or similar. Return counts per language.`,
  max_tool_calls: 5,
  tools: ['shell.run'],
})

// Phase 2: Extract with SIMD
const extractResult = await agent({
  role: 'explore',
  task: `Run the repomap SIMD extractor on ${WORKSPACE}:
  cd /home/dev/whale && go test -run=XXX -bench=BenchmarkRealCodebaseSIMD -benchtime=1x -count=1 ./internal/repomap/ 2>&1
  
  Also run:
  cd /home/dev/whale && go test -run=TestPluginStartupContext -v ./internal/repomap/ 2>&1
  
  Return the symbol counts and any errors.`,
  max_tool_calls: 10,
  tools: ['shell.run'],
})

// Phase 3: Report
const report = await agent({
  role: 'review',
  task: `Compare the repomap results:
  
  Scan results:
  ${scanResult}
  
  Extraction results:
  ${extractResult}
  
  ${PREVIOUS ? `Previous results:\n${PREVIOUS}` : 'No previous results to compare.'}
  
  Produce a report with:
  - Total files per language
  - Total symbols extracted
  - Symbols per file average
  - Any files with zero symbols (possible parser gaps)
  - Comparison with previous run (if available)
  - Recommendations
  
  Keep it concise — bullet points.`,
  max_tool_calls: 5,
})

return {
  workspace: WORKSPACE,
  scan: scanResult,
  extraction: extractResult,
  report: report,
  timestamp: new Date().toISOString(),
}

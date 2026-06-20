export const meta = {
  name: 'release-check',
  defaultBudgetTokens: 250000,
  description: 'Pre-release checklist — run full test suite, check docs are updated, verify build artifacts, check git tags.',
  whenToUse: 'Before tagging a release. Runs comprehensive checks to ensure nothing is broken.',
  phases: [
    { title: 'Build', detail: 'Build all artifacts' },
    { title: 'Test', detail: 'Run full test suite' },
    { title: 'Docs', detail: 'Check docs are updated, no dead links' },
    { title: 'Git', detail: 'Check changelog, tag consistency' }
  ],
}

const VERSION = args.version || 'HEAD'

// Phase 1: Build everything
const buildResult = await agent({
  role: 'explore',
  task: `Build all project artifacts on dev-cx53:
  1. cd /home/dev/vaked-base && nix develop .# --command bash -c "go build ./internal/repomap/"
  2. Verify the repomap package compiles
  3. Check that no build warnings are present
  Return: BUILD_OK or BUILD_FAIL with details.`,
  max_tool_calls: 8,
  tools: ['shell.run'],
})

// Phase 2: Run tests
const testResult = await agent({
  role: 'explore',
  task: `Run the test suite on dev-cx53:
  1. cd /home/dev/whale && go test ./internal/repomap/ -v -count=1
  2. cd /home/dev/whale && go test ./internal/plugins/ -v -count=1
  3. Report any failures with full output
  
  Return: TESTS_PASS or TESTS_FAIL with failing test names.`,
  max_tool_calls: 15,
  tools: ['shell.run'],
})

// Phase 3: Check docs
const docsResult = await agent({
  role: 'explore',
  task: `Check documentation health:
  1. Read docs/whale-ultra-bench.md and verify it matches docs/whale-ultra-bench.html
  2. Check that .whale/config.toml and .whale/mcp.json are valid JSON/TOML
  3. Verify CHANGELOG.md exists and has an entry for version ${VERSION}
  
  Return: DOCS_OK or DOCS_ISSUES with specific problems.`,
  max_tool_calls: 10,
  tools: ['workspace.read'],
})

// Phase 4: Git checks
const gitResult = await agent({
  role: 'explore',
  task: `Git pre-release checks:
  1. git log --oneline -10 — are recent commits well-described?
  2. git tag -l — is the version tag already used?
  3. git status — is the working tree clean?
  
  Return: GIT_OK or GIT_ISSUES with specific problems.`,
  max_tool_calls: 5,
  tools: ['shell.run'],
})

const allPass = !buildResult.includes('FAIL') && !testResult.includes('FAIL') && !docsResult.includes('ISSUES') && !gitResult.includes('ISSUES')

return {
  version: VERSION,
  build: buildResult,
  tests: testResult,
  docs: docsResult,
  git: gitResult,
  ready: allPass ? 'YES — safe to release' : 'NO — fix issues before releasing',
  timestamp: new Date().toISOString(),
}

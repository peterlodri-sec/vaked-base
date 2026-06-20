export const meta = {
  name: 'pr-review',
  description: 'Automated PR review — fetch diff, check for bugs, security issues, style, and produce a structured review with severity ratings.',
  whenToUse: 'When a PR number is given (e.g., "review PR #356"). Fetches the diff, runs analysis phases, posts review summary.',
  phases: [
    { title: 'Fetch', detail: 'Fetch PR diff via GitHub MCP' },
    { title: 'Analyze', detail: 'Security, bugs, style, performance checks' },
    { title: 'Report', detail: 'Structured review with severity: critical/high/medium/low' }
  ],
}

const PR_NUMBER = args.pr || args.number

if (!PR_NUMBER) {
  throw new Error('pr-review requires args.pr or args.number')
}

// Phase 1: Fetch PR diff
const diff = await agent({
  role: 'explore',
  task: `Fetch the diff for PR #${PR_NUMBER} from github.com/peterlodri-sec/vaked-base. Use GitHub MCP to get the PR files changed and their diffs. Return the complete diff with file paths.`,
  max_tool_calls: 10,
})

// Phase 2: Analyze
const analysis = await agent({
  role: 'review',
  task: `Review this PR diff and identify:
1. Security issues (injection, exposed secrets, unsafe input handling)
2. Bugs (logic errors, nil derefs, race conditions, incorrect error handling)
3. Style issues (naming, consistency with project conventions)
4. Performance issues (unnecessary allocations, blocking calls)

For each finding, assign: severity (critical/high/medium/low), file:line, description.

PR diff:
${diff}`,
  max_tool_calls: 15,
})

// Phase 3: Report
return {
  pr: PR_NUMBER,
  summary: analysis,
  recommendation: analysis.includes('critical') ? 'BLOCK' : analysis.includes('high') ? 'REVIEW_REQUIRED' : 'APPROVE',
  timestamp: new Date().toISOString(),
}

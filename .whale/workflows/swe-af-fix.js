export const meta = {
  name: 'swe-af-fix',
  description: 'End-to-end SWE agent fix — given a GitHub issue, branch, implement fix, verify with tests, create PR.',
  whenToUse: 'When given an issue number and a clear fix description. Handles the full cycle: read issue → plan → implement → test → PR.',
  phases: [
    { title: 'Understand', detail: 'Read issue, understand the problem' },
    { title: 'Plan', detail: 'Create implementation plan' },
    { title: 'Implement', detail: 'Write the code fix' },
    { title: 'Verify', detail: 'Run tests, verify fix works' },
    { title: 'Ship', detail: 'Commit, push, create PR' }
  ],
}

const ISSUE = args.issue

if (!ISSUE) {
  throw new Error('swe-af-fix requires args.issue (GitHub issue number)')
}

// Phase 1: Understand
const issueContext = await agent({
  role: 'explore',
  task: `Read issue #${ISSUE} from github.com/peterlodri-sec/vaked-base. Get the full issue body, any linked PRs, and understand the problem. Also check if there are any existing attempts or comments with solutions. Return a clear summary of what needs to be fixed.`,
  max_tool_calls: 10,
})

// Phase 2: Plan
const plan = await agent({
  role: 'review',
  task: `Given this issue, create a concrete implementation plan:
  
  Issue: ${issueContext}
  
  Plan should include:
  - Which files need to change
  - What the fix looks like (pseudocode or description)
  - What tests need to pass
  - Any risks or side effects
  
  Be specific — this plan will be executed by a coding agent.`,
  max_tool_calls: 8,
})

// Phase 3: Implement
const implementation = await agent({
  role: 'explore',
  task: `Implement the fix according to this plan. Use write/edit/multi_edit tools to make the changes.
  
  Plan:
  ${plan}
  
  After making changes, verify the files compile (go build or python3 -m py_compile or zig build as appropriate).`,
  max_tool_calls: 25,
  tools: ['workspace.read', 'workspace.write', 'shell.run'],
})

// Phase 4: Verify
const verification = await agent({
  role: 'explore',
  task: `Run the relevant tests to verify the fix works:
  1. Run unit tests for the changed files
  2. Check that existing tests still pass
  3. If there is a reproduction case from the issue, verify it is now fixed
  
  Implementation result:
  ${implementation}
  
  Return: PASS (all tests pass), FAIL (tests fail with details), or SKIP (no tests available).`,
  max_tool_calls: 15,
  tools: ['shell.run'],
})

// Phase 5: Ship
const prResult = await agent({
  role: 'explore',
  task: `The fix is implemented and verified. Create a PR:
  1. Create a branch named fix/issue-${ISSUE}-auto
  2. Commit with message: "fix: resolves #${ISSUE} — [brief description]"
  3. Push the branch
  4. Create a PR with title including "Closes #${ISSUE}"
  5. Return the PR URL
  
  Verification result: ${verification}
  Implementation summary: ${implementation}`,
  max_tool_calls: 12,
  tools: ['shell.run'],
})

return {
  issue: ISSUE,
  plan: plan,
  verification: verification,
  pr: prResult,
  timestamp: new Date().toISOString(),
}

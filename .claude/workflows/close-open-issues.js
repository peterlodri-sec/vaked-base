// close-open-issues — triage every open issue, fix the genuinely-open scoped ones,
// close the already-done ones with evidence, defer epics/design. NEVER auto-merges:
// fixes land as DRAFT PRs (fleet-safe: non-fleet author, no train:auto label).
//
// Lesson baked in (from manual triage of #7/#25/#58/#59 in this repo): an active
// agent fleet means "open" != "unimplemented" — most open issues are already fixed,
// or are multi-week epics/design. Blindly "fixing every open issue" produces noise;
// triage FIRST, act only on the genuinely-open + single-scoped.
//
// Run: Workflow({ name: 'close-open-issues' })  — from a vaked-base checkout.

export const meta = {
  name: 'close-open-issues',
  description: 'Triage open issues; fix scoped-open ones as draft PRs, close already-done ones with evidence, defer epics. Never auto-merges.',
  phases: [
    { title: 'Discover' },
    { title: 'Triage' },
    { title: 'Act' },
  ],
}

const REPO = 'peterlodri-sec/vaked-base'

const ISSUES_SCHEMA = {
  type: 'object', required: ['issues'], additionalProperties: false,
  properties: {
    issues: {
      type: 'array',
      items: {
        type: 'object', required: ['number', 'title'], additionalProperties: true,
        properties: { number: { type: 'integer' }, title: { type: 'string' }, labels: { type: 'array', items: { type: 'string' } } },
      },
    },
  },
}

const TRIAGE_SCHEMA = {
  type: 'object', required: ['number', 'verdict', 'reason'], additionalProperties: false,
  properties: {
    number: { type: 'integer' },
    verdict: { type: 'string', enum: ['done', 'fixable', 'defer'] },
    reason: { type: 'string' },
    evidence: { type: 'string', description: 'for done: file:line proof the fix is already in main' },
  },
}

const ACT_SCHEMA = {
  type: 'object', required: ['number', 'action', 'outcome'], additionalProperties: false,
  properties: {
    number: { type: 'integer' },
    action: { type: 'string', enum: ['draft_pr', 'closed_with_evidence', 'deferred', 'failed'] },
    outcome: { type: 'string' },
    pr: { type: 'string', description: 'draft PR url if action=draft_pr' },
    verify_cmd: { type: 'string' },
  },
}

phase('Discover')
const disc = await agent(
  `List EVERY open issue in ${REPO}. Run: gh issue list -R ${REPO} --state open --limit 100 --json number,title,labels. ` +
  `Return them as {issues:[{number,title,labels}]} (labels = array of label name strings).`,
  { label: 'discover', phase: 'Discover', schema: ISSUES_SCHEMA })

const issues = (disc?.issues || [])

// Pipeline each issue independently: triage -> act. No barrier (each issue flows
// alone), so a slow fix never blocks triage of the rest. Worktree isolation on the
// Act stage prevents parallel fixers colliding in the working tree.
const results = await pipeline(
  issues,
  // Stage 1 — triage (read-only): is it already fixed in main, scoped-fixable, or an epic/design to defer?
  (iss) => agent(
    `Triage issue #${iss.number} ("${iss.title}", labels: ${(iss.labels || []).join(',') || 'none'}) in ${REPO}.\n` +
    `Read it (gh issue view ${iss.number} -R ${REPO}) AND check main: is the fix already present (search the code), is it a single-scoped genuinely-open bug/feature, or a multi-week epic / design-only / blocked issue?\n` +
    `verdict: "done" (already in main — give file:line evidence), "fixable" (scoped + implementable now), or "defer" (epic/design/blocked). Be skeptical: prefer "done"/"defer" unless clearly single-scoped.`,
    { label: `triage#${iss.number}`, phase: 'Triage', schema: TRIAGE_SCHEMA }
  ).then(t => ({ ...t, _iss: iss })),
  // Stage 2 — act on the verdict.
  (t) => {
    if (!t) return null
    if (t.verdict === 'defer')
      return { number: t.number, action: 'deferred', outcome: t.reason }
    if (t.verdict === 'done')
      return agent(
        `Issue #${t.number} appears already fixed: ${t.evidence || t.reason}. VERIFY that evidence against main; if confirmed, post a verification comment citing it and close the issue (gh issue close ${t.number} -R ${REPO} -c "<evidence>"). If NOT actually fixed, do nothing and report action=failed.`,
        { label: `close#${t.number}`, phase: 'Act', schema: ACT_SCHEMA })
    // fixable: implement in an isolated worktree, verify locally, open a DRAFT PR. Never merge.
    return agent(
      `Fix issue #${t.number} in ${REPO}. ${t.reason}\n` +
      `Work in an isolated git worktree/branch off main. Write a regression test that FAILS without the fix and PASSES with it (CLAUDE.md rule 5). Verify locally (cargo test / zig build / pytest as appropriate — dev-cx53 is off-limits, verify on this host). Open a DRAFT PR referencing #${t.number}. Do NOT merge, do NOT add a train:auto label (fleet-safety). Report the PR url + the exact verify_cmd you ran.`,
      { label: `fix#${t.number}`, phase: 'Act', schema: ACT_SCHEMA, isolation: 'worktree' })
  }
)

const acted = results.filter(Boolean)
const by = (a) => acted.filter(r => r.action === a)
return {
  open_issues: issues.length,
  draft_prs: by('draft_pr'),
  closed_with_evidence: by('closed_with_evidence'),
  deferred: by('deferred'),
  failed: by('failed'),
  summary: `triaged ${acted.length}/${issues.length}: ${by('draft_pr').length} draft-PR'd, ${by('closed_with_evidence').length} closed-with-evidence, ${by('deferred').length} deferred, ${by('failed').length} failed`,
}

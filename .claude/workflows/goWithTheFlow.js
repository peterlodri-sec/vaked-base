export const meta = {
  name: 'goWithTheFlow',
  description: 'Evolve our agents toward nullclaw (fastest/smallest/fully-autonomous Zig): study the rubric once, then per-agent evolve -> verify gate (X) -> (gated) Zig-migration sketch.',
  phases: [
    { title: 'Study' },
    { title: 'Evolve' },
    { title: 'Verify' },
    { title: 'Migrate' },
  ],
}

// The nullclaw evolution rubric (study once, feed every agent).
const RUBRIC_SCHEMA = {
  type: 'object', required: ['traits', 'zig_patterns'], additionalProperties: false,
  properties: {
    traits: {
      type: 'array',
      items: {
        type: 'object', required: ['name', 'signal'], additionalProperties: false,
        properties: { name: { type: 'string' }, signal: { type: 'string' } },
      },
    },
    zig_patterns: { type: 'array', items: { type: 'string' } },
  },
}

const PROPOSAL_SCHEMA = {
  type: 'object',
  required: ['agent', 'changes', 'autonomy_score'], additionalProperties: false,
  properties: {
    agent: { type: 'string' },
    changes: { type: 'array', items: { type: 'string' } },
    faster: { type: 'string' },
    smaller: { type: 'string' },
    more_autonomous: { type: 'string' },
    autonomy_score: { type: 'integer' },
  },
}

const VERDICT_SCHEMA = {
  type: 'object', required: ['pass', 'reason'], additionalProperties: false,
  properties: { pass: { type: 'boolean' }, reason: { type: 'string' } },
}

const MIGRATE_SCHEMA = {
  type: 'object', required: ['agent', 'zig_sketch'], additionalProperties: false,
  properties: {
    agent: { type: 'string' },
    zig_sketch: { type: 'string' },
    modules: { type: 'array', items: { type: 'string' } },
  },
}

// Our evolvable agents. Override via args: ["ralph", "eventd", ...].
const AGENTS = (Array.isArray(args) && args.length) ? args : [
  'ralph (decide/run/watch decision loop, tools/ralph)',
  'flow-driver control plane (pause/slow/rewind/jump + hash-chained event log)',
  'eventd (append-only hash-chained event log; docs/superpowers/specs/2026-06-12-eventd-design.md)',
  'agent-supervisord (OTP supervision tree from parallel/fiber; gen/otp/*.supervision.json)',
  'nullclaw sentinel (#9 OS-log eBPF evidence daemon)',
]

phase('Study')
const rubric = await agent(
  'Study github.com/nullclaw/nullclaw ("fastest, smallest, fully-autonomous AI assistant infrastructure", Zig, ~7.7k stars). Read its README / AGENTS.md / CLAUDE.md / build.zig via gh or web. Extract the concrete TRAITS that make it fast, small, and FULLY AUTONOMOUS (each: name + the observable signal), and the Zig architecture patterns it uses. Return the rubric — grounded in the actual repo, not generic.',
  { schema: RUBRIC_SCHEMA, phase: 'Study' },
)
const rubricText = JSON.stringify(rubric)

// Per-agent: evolve -> verify gate (X) -> (gated) Zig migration. pipeline so each
// agent streams independently; later stages receive (prevResult, originalItem, index).
const results = await pipeline(
  AGENTS,
  // EVOLVE (option 3): how to push this agent toward the rubric.
  (a) => agent(
    `nullclaw evolution rubric:\n${rubricText}\n\nEvolve OUR agent "${a}" toward it. Read the agent's real current shape in the repo first. Propose concrete changes that make it faster, smaller, and MORE AUTONOMOUS in the nullclaw style — no hand-waving. Score the resulting autonomy 1-10 (10 = fully autonomous, no human in the turn).`,
    { schema: PROPOSAL_SCHEMA, phase: 'Evolve', label: `evolve:${a.split(' ')[0]}` },
  ),
  // VERIFY GATE = "X": adversarially confirm the proposal is real AND autonomous enough.
  (proposal, a) => agent(
    `Adversarially verify this evolution proposal for "${a}":\n${JSON.stringify(proposal)}\n\nIs every change grounded in the agent's real code (not aspirational), and does it actually reach fully-autonomous (autonomy_score >= 8)? Default pass=false if uncertain.`,
    { schema: VERDICT_SCHEMA, phase: 'Verify', label: `verify:${a.split(' ')[0]}` },
  ).then((verdict) => ({ agent: a, proposal, verdict })),
  // MIGRATE (option 2) — runs only AFTER X (gate passed): draft the Zig migration.
  async (gated) => {
    if (!gated || !gated.verdict || !gated.verdict.pass) return gated
    const sketch = await agent(
      `"${gated.agent}" passed the autonomy gate. Draft a Zig migration sketch (modules + key types/functions, nullclaw-style: fast + small) realizing:\n${JSON.stringify(gated.proposal)}\nA concrete module/type plan, not a code dump.`,
      { schema: MIGRATE_SCHEMA, phase: 'Migrate', label: `migrate:${gated.agent.split(' ')[0]}` },
    )
    return { ...gated, zig_sketch: sketch }
  },
)

return { rubric, results: results.filter(Boolean) }

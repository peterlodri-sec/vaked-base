// AI-lish V1 driver — builds the parser/guardrail (Phase B) + optimizer (Phase C)
// from the RFC at docs/ailish/2026-06-14-ailish-v1-rfc.md (Phase A, already written).
// Agents are pure producers: they READ the RFC + return file contents as structured
// JSON; the orchestrator (or the human running this) writes + `cargo test`s the result.
// Run:  Workflow({ name: "ailish-v1-drive" })   (from a checkout of vaked-base)

export const meta = {
  name: 'ailish-v1-drive',
  description: 'Build the AI-lish V1 nom parser + guardrail (Phase B) and ailishfmt + token-compaction (Phase C) from the RFC',
  phases: [
    { title: 'Parser', detail: 'nom parser + typed AST + register-monad guardrail + tests' },
    { title: 'Optimize', detail: 'ailishfmt idempotent formatter + §5 compaction map + token benchmark' },
    { title: 'Verify', detail: 'cargo test + completeness critic vs the RFC' },
  ],
}

const RFC = 'docs/ailish/2026-06-14-ailish-v1-rfc.md'

const FILES_SCHEMA = {
  type: 'object',
  required: ['files', 'verify_cmd', 'notes'],
  properties: {
    files: {
      type: 'array',
      items: {
        type: 'object',
        required: ['path', 'content'],
        properties: { path: { type: 'string' }, content: { type: 'string' } },
      },
    },
    verify_cmd: { type: 'string' },
    notes: { type: 'string' },
  },
}

const CRITIC_SCHEMA = {
  type: 'object',
  required: ['covered', 'missing', 'pr_ready'],
  properties: {
    covered: { type: 'array', items: { type: 'string' } },
    missing: { type: 'array', items: { type: 'string' }, description: 'RFC rule/grammar production with no parser support or no test' },
    pr_ready: { type: 'boolean' },
  },
}

const BASE = `You are building the AI-lish V1 reference implementation in a NEW Rust crate at tools/ailish/.
Read the normative spec first: ${RFC} (grammar §2, register monads §3, lowering example §4, compaction §5).
PURE PRODUCER: read files, RETURN full file contents as structured output; do NOT git/commit. Edition 2021. Warning-free. nom is the only parser dep (pin a current version and commit Cargo.lock so a --locked CI build is reproducible — the repo's ci-gate rust-build runs cargo test --locked).`

phase('Parser')
const parser = await agent(`${BASE}

TASK (Phase B): implement the parser + guardrail. Files: tools/ailish/Cargo.toml, tools/ailish/Cargo.lock, tools/ailish/src/lib.rs (+ modules as needed), tools/ailish/tests/parse.rs.
- A typed AST: Frame{register, lines:Vec<Line>}, Line = SsaAssign{var,Expr} | Stmt(Relation|Gate|Schedule). Variable = %N. Operands = Var | TypedAtom(Literal|Env|Path|Symbol). Verbs/funcs/gate enums per §2.
- A nom parser: text -> Vec<Frame>. Accept BOTH long ([R:bench]) and compact ([!B]) register forms (§5). Reject malformed frames with a typed error carrying byte offset.
- A guardrail pass over parsed frames enforcing §3 register monads: R:plan may schedule but not invoke side-effecting verbs; R:risk must emit gate(*:fail) or a mitigation; R:commit must be frozen if any gate(*:fail) is live. Return a Vec of violations.
- tests/parse.rs: parse the §4 V1 lowering example exactly; round-trip a few frames; assert each §3 violation is caught; assert compact==long parse equivalence.
verify_cmd: "cd tools/ailish && cargo test --locked".`,
  { label: 'parser', phase: 'Parser', schema: FILES_SCHEMA })

const parserLib = (parser?.files || []).map(f => `// ${f.path}\n${f.content}`).join('\n\n')

phase('Optimize')
const optimize = await agent(`${BASE}

The parser/AST/guardrail crate was just produced. Build the optimizer ON its public API. Current crate files:
<<<CRATE
${parserLib.slice(0, 24000)}
CRATE

TASK (Phase C): add tools/ailish/src/fmt.rs (+ wire into lib.rs) and tools/ailish/tests/fmt.rs:
- ailishfmt: AST -> canonical text, in BOTH long and compact modes, IDEMPOTENT (fmt(fmt(x))==fmt(x)).
- the §5 compaction map (registers + operator->function); fmt(compact) and fmt(long) of the same AST must parse-equal.
- a token-count helper + a test that measures long-vs-compact char/token delta on the §4 example and asserts compact < long.
verify_cmd: "cd tools/ailish && cargo test --locked".`,
  { label: 'optimize', phase: 'Optimize', schema: FILES_SCHEMA })

phase('Verify')
const critic = await agent(`${BASE}

Two phases produced a tools/ailish crate (parser+guardrail, then fmt+compaction). As a COMPLETENESS CRITIC, read ${RFC} and judge coverage. List every §2 grammar production and §3 register rule, mark which have BOTH parser support and a test, and which are missing either. Be specific and skeptical. Do not write code.`,
  { label: 'critic', phase: 'Verify', schema: CRITIC_SCHEMA })

return {
  files: [...(parser?.files || []), ...(optimize?.files || [])],
  critic,
}

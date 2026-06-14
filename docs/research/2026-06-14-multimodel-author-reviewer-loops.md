# Deep-research report B — Multi-model author/reviewer coding loops: does a strong author + cheaper reviewer pay off?

Date: 2026-06-14 · Harness: `deep-research` (fan-out → fetch → adversarial verify → synthesize)
· Batch: PR-pipeline dogfood (`claude/vaked-pr-pipeline-dogfood-pdl4sk`)

> **Why this question.** The dogfood example's **workflow pr_loop** is the
> *ordering graph*: `collect → implement → review → publish → checkin`, with the
> fix-loop modeled as **retries on `implement`**, not a back-edge. The author is a
> strong model (`claude-opus-4-8`); the reviewer is a cheaper one
> (`gemini-3.1-flash-lite`, `fs.repo_ro`). This report asks whether that split is
> empirically justified and whether "retries, not cycles" is the right shape.

## Question

> Heterogeneous multi-model agentic coding loops (2024–2026): does pairing a
> strong "author" model with a separate (possibly cheaper) "reviewer/critic"
> model measurably improve PR correctness? When does a cheaper model preserve
> quality while cutting cost, and how should iterative fix-loops be modeled —
> bounded retries vs. back-edges?

## Method

Three search angles (author/reviewer correctness gains · model-routing cost/
quality · static DAG verification & fix-loop modeling), each a parallel fan-out
of WebSearch + WebFetch over 4–6 authoritative sources (arXiv, SWE-bench work,
orchestrator docs), claims extracted as falsifiable statements, ranked by source
quality and corroboration, disagreements surfaced. Confidence: **HIGH / MED /
LOW** as in report A.

## Findings

### 1. A separate reviewer/critic measurably improves correctness

- **[HIGH]** OpenAI's **CriticGPT**: model critiques were preferred over human
  critiques 63% of the time on naturally-occurring LLM code errors, and >80% on
  inserted bugs — a separately-tasked critic catches more than humans alone.
  *arXiv:2407.00215 (2024-06).*
- **[HIGH]** Critic + human teams match the critic's bug-catch rate with **fewer
  hallucinated bugs** — i.e. the human's value shifts to filtering reviewer
  over-reach (false positives are a real, measurable risk). *arXiv:2407.00215.*
- **[MED]** Role-splitting alone (Manager/Researcher/Engineer/Reviewer) reported
  **72.2% on SWE-bench Verified vs ~65%** single-agent at the same model class —
  ~+7 pts attributed to team structure. *dev.to "Agyn" (2026-03) — vendor-
  adjacent, not peer-reviewed; doesn't isolate a *different*-model reviewer.*
- **[MED]** AgentCoder (programmer + separate test-designer + executor):
  **79.9% pass@1 on HumanEval with GPT-3.5** vs 57.3% base; 91.5% mean pass@1 with
  GPT-4. *arXiv:2312.13010 — roles often the same underlying model, so this shows
  role-separation value more than cross-model value.*

### 2. Cross-model review beats self-review — by large margins

- **[HIGH]** "Self-Correction Illusion": relabeling an error from the model's own
  context to an *external* role lifted correction rates by **23–93 pp** across 13
  model-domain tests (e.g. Llama-3.3-70B 0%→93%; significant in 10/13, p<0.001) —
  models fix others' errors but miss identical errors in their own traces.
  *arXiv:2606.05976 — reasoning/math tasks, not pure code.*
- **[HIGH]** Self-critique scores run systematically lower than cross-model
  critique (DeepSeek-R1 ~36% lower self-evaluation); single-agent self-review
  repeats original errors (the "homogenisation trap"). *arXiv:2502.19361.*
- **[HIGH]** Foundational caveat: intrinsic self-correction *without external
  feedback* often does **not** help and can degrade performance — the base case
  for using any external reviewer at all. *Huang et al., ICLR 2024,
  arXiv:2310.01798.*

> **Maps to Vaked.** The dogfood deliberately uses a *different family* for review
> (`gemini-*` reviewing `opus-*` output). The literature's strongest, most
> statistically-significant result directly backs "never self-grade."

### 3. The reviewer need NOT be as strong as the author — with one caveat

- **[HIGH]** Ensembling cheap/weak verifiers (Weaver) reached **o3-mini-level
  selection accuracy (86.2%)** using cheap Llama-3.3-70B — combining weak
  verifiers matches a top reviewer. *openreview dRjt4vlYVQ; arXiv:2506.10056.*
- **[HIGH] — partial disagreement:** for a *single*-judge code verification,
  stronger judges are meaningfully more reliable; small/open judges misclassify
  buggy code as correct. *arXiv:2507.10535 (CodeJudgeBench); arXiv:2604.16790.*
- **Reconciliation:** a cheaper reviewer is sound **as an ensemble or a first-
  stage filter**, *not* as a lone authoritative judge.

### 4. Cost/quality of a cheaper stage — real savings, sharp caveats

- **[HIGH]** Query-level **cascades** (FrugalGPT) matched GPT-4-class accuracy at
  **up to ~98% cost reduction** on its benchmarks (best-case; task-dependent).
  *arXiv:2305.05176.*
- **[HIGH]** **RouteLLM** cut cost ~85% on MT-Bench at 95% of GPT-4 quality — but
  only ~35% on GSM8K and routed 54% of MMLU calls to the strong model: savings are
  **highly task-dependent**. *lmsys.org 2024-07; arXiv:2406.18665.*
- **[HIGH]** Two-tier routing in a multi-agent extraction pipeline: **51% cost cut
  at 98.2% accuracy retention**; hierarchical supervisor/worker: 98.5% of best F1
  at 60.7% of cost. *arXiv:2603.22651.*
- **[HIGH] — the load-bearing caveat:** cheap models make **poor verifiers** —
  ≥96% true-positive but **<25% true-negative** rate (they rubber-stamp), are
  overconfident (breaking a cascade's deferral signal), and are brittle to style/
  adversarial shifts (up to +0.24 false-negative on style changes; 100% FN under
  some adversarial inputs). *arXiv:2511.19933; arXiv:2502.19335 (GATEKEEPER);
  arXiv:2503.05061.*

> **Maps to Vaked.** The dogfood reviewer is **advisory and read-only**
> (`fs.repo_ro`, no publish grant) — it cannot rubber-stamp a merge because it
> holds no merge authority; the broker publishes. That structure neatly sidesteps
> the "cheap judge rubber-stamps" failure mode: the cheap reviewer informs, the
> graph (and broker) decide. For a *blocking* gate, the evidence says use an
> ensemble or a stronger judge, plus a non-LLM evidence layer (tests/SAST), which
> caught 47% of bugs LLM reviewers missed (→96.9% detection). *arXiv:2602.16741.*

### 5. Fix-loops: bounded retries, not back-edges

- **[HIGH]** Classical orchestrators (Airflow, Dagster, Dagger) enforce **strict
  acyclicity** at graph-load / structurally and have no loop primitive
  (`AirflowDagCycleException`; "assets dependencies form a cycle"; content-
  addressed DAG). *github.com/apache/airflow#17079; dagster.io; docs.dagger.io.*
- **[HIGH]** Agent frameworks (LangGraph, Temporal, Step Functions, CrewAI)
  deliberately permit iteration and bound it only at **runtime** — LangGraph
  `recursion_limit` (default 25), Temporal retry policy (**MaximumAttempts default
  = unlimited** — a documented footgun), Step Functions history-event quotas,
  CrewAI `max_iter`. *langchain docs; docs.temporal.io; AWS docs; crewAI#56.*
- **[HIGH]** **Agentproof** (the most on-topic source) does genuine *pre-
  deployment* static checks — **acyclicity, depth bounds, critical-path** — across
  LangGraph/CrewAI/AutoGen/ADK, and **explicitly distinguishes legitimate bounded
  retries (fix-loops with iteration caps) from problematic back-edges**, modeling
  fix-loops as bounded retries. *arXiv:2603.20356 — 27% of 18 workflows had
  structural defects, 55% violated a human-gate policy; numbers single-source.*

> **Maps to Vaked.** This is the dogfood's exact choice: a checked DAG (depth 5)
> with the fix-loop as **`retries` on `implement`**, not a `checkin → collect`
> back-edge — and the negative tests prove it (`E-WORKFLOW-CYCLE` on an injected
> back-edge, `E-WORKFLOW-DEPTH` at `maxDepth=3`). Vaked does this at *compile
> time*; every framework above except Agentproof bounds loops only at runtime, and
> Temporal's "unlimited by default" is precisely the hazard a finite, declared
> retry cap removes.

## Disagreements / caveats

- **Reviewer strength:** "cheap ensemble suffices" (Weaver) vs. "single weak judge
  unreliable" (CodeJudgeBench). Resolved by *role*: cheap is fine as ensemble /
  first-stage filter / advisory, risky as a lone blocking judge.
- **Self- vs. cross-review:** "self-verification works" (ReVeal, arXiv:2506.11442)
  sits in tension with the self-correction-illusion results; the reconciling
  variable is whether the verifier receives an *external* signal (tests, a
  different role/model) rather than pure introspection.
- **Single-source 2026 preprints:** the sharpest numbers (Agentproof's 27%/55%/
  sub-second-at-5k; the +7-pt SWE-bench team result) are author-reported and not
  independently reproduced — suggestive, not settled.

## Bottom line for the dogfood

The PR's ordering graph is **strongly supported**: a distinct, different-family
reviewer (never self-grading) is the single best-evidenced design choice, and
making the reviewer **advisory + read-only** rather than a blocking cheap judge
sidesteps the literature's biggest cheap-model failure mode (rubber-stamping).
Modeling the fix-loop as **bounded retries on `implement`** rather than a
back-edge matches both classical-orchestrator acyclicity and the most on-topic
2026 static-verification work — and doing the cycle/depth check at *compile time*
is ahead of the runtime-only bounds in every shipping agent framework surveyed.
The one improvement the evidence points to: for any *blocking* quality gate, back
the LLM reviewer with a non-LLM evidence layer (tests/SAST), which recovers the
bug classes LLM reviewers structurally miss.

## Sources

- CriticGPT — https://arxiv.org/html/2407.00215v1
- Coding agent teams on SWE-bench Verified — https://dev.to/nikita_benkovich_eb86e54d/coding-agent-teams-outperform-solo-agents-722-on-swe-bench-verified-4of5
- AgentCoder — https://arxiv.org/pdf/2312.13010
- Self-Correction Illusion — https://arxiv.org/html/2606.05976
- Self- vs cross-model evaluation — https://arxiv.org/pdf/2502.19361
- LLMs Cannot Self-Correct Reasoning Yet (ICLR'24) — https://arxiv.org/abs/2310.01798
- Weaver (weak-verifier ensembling) — https://openreview.net/forum?id=dRjt4vlYVQ · https://arxiv.org/html/2506.10056v1
- CodeJudgeBench — https://arxiv.org/pdf/2507.10535
- Bias in the Loop — https://arxiv.org/html/2604.16790v1
- FrugalGPT — https://arxiv.org/abs/2305.05176
- RouteLLM — https://www.lmsys.org/blog/2024-07-01-routellm/ · https://arxiv.org/pdf/2406.18665
- Multi-agent extraction cost/quality — https://arxiv.org/html/2603.22651
- Cheap-verifier agreeableness bias — https://arxiv.org/pdf/2511.19933
- GATEKEEPER (confidence calibration) — https://arxiv.org/pdf/2502.19335
- Small-judge brittleness — https://arxiv.org/html/2503.05061v1
- LLM reviewer blind spots + SAST backstop — https://arxiv.org/html/2602.16741v1
- ReVeal (generation-verification loop) — https://arxiv.org/html/2506.11442v1
- Agentproof: Static Verification of Agent Workflow Graphs — https://arxiv.org/pdf/2603.20356
- Airflow cycle detection — https://github.com/apache/airflow/issues/17079
- Temporal retry policies — https://docs.temporal.io/encyclopedia/retry-policies
- AWS Step Functions static validation — https://docs.aws.amazon.com/step-functions/latest/apireference/API_ValidateStateMachineDefinitionDiagnostic.html
- LangGraph recursion limit — https://docs.langchain.com/oss/python/langgraph/errors/GRAPH_RECURSION_LIMIT
- Dagster DAG glossary — https://dagster.io/glossary/dag-directed-acyclic-graph

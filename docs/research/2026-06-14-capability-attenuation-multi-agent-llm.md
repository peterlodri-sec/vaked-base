# Deep-research report A — Capability attenuation & least-privilege for heterogeneous multi-agent LLM systems

Date: 2026-06-14 · Harness: `deep-research` (fan-out → fetch → adversarial verify → synthesize)
· Batch: PR-pipeline dogfood (`claude/vaked-pr-pipeline-dogfood-pdl4sk`)

> **Why this question.** The dogfood example's **mesh field** is the *authority
> graph*: an operator delegates **attenuated** capabilities to an author
> (`fs.repo_rw`, no publish), a reviewer (`fs.repo_ro` only), and a **sole
> publisher** broker (`mcp.github_write`). This report asks whether that design
> reflects the state of the art for least-privilege delegation across LLM agents
> running different models, and where the known failure modes are.

## Question

> Least-privilege capability attenuation in heterogeneous multi-agent LLM
> systems (2025–2026): the state of the art for delegating attenuated/scoped
> capabilities from an operator to LLM agents on different models — object-
> capability (ocap) models, POLA, MCP authorization and tool-scoping, the
> sole-publisher / single-writer broker pattern, and static verification of
> delegation. Including failure modes: confused-deputy, capability widening,
> prompt-injection-driven privilege escalation.

## Method

Three search angles (ocap/POLA for agents · MCP authorization & tool-scoping ·
broker pattern & injection defense), each a parallel fan-out of WebSearch +
WebFetch over 4–6 authoritative sources, claims extracted as falsifiable
statements, then ranked by source quality and cross-corroboration. Confidence
tags: **HIGH** (authoritative + corroborated), **MED** (single credible source
or contested), **LOW** (adjacent / weak source). Disagreements are surfaced, not
smoothed.

## Findings

### 1. Attenuation-only delegation is the convergent model

- **[HIGH]** Authority can only *narrow* down a delegation chain — at each hop,
  scope narrows or stays equal, never widens; verifiers must check attenuation at
  *every hop* across tools, budget, domains, and time.
  *IETF draft-prakash-aip-00 (2026-03-27), corroborated by arXiv:2603.24775.*
- **[HIGH]** A child's effective authority is the **subset/intersection** of the
  parent's grant and the child's own policy; re-delegation can only restrict
  further. This is textbook object-capability semantics now applied to agents.
  *arXiv:2603.21354 (concept), arXiv:2603.00195, arXiv:2603.24775.*
- **[HIGH]** Concrete credential primitives implement this: **macaroons** /
  **Biscuit** tokens attenuate by appending narrowing caveats and verify offline,
  vs. amplifiable identity-based API keys; AIP's Invocation-Bound Capability
  Tokens fuse identity + attenuated authorization + provenance (compact JWT for
  single-hop, chained Biscuit for multi-hop).
  *arXiv:2603.24775; CSA blog 2026-03-25; dev.to/mattdeangit.*

> **Maps to Vaked.** The mesh field's attenuation check
> (`E-CAP-ATTENUATION`, design 0011 §4.4) *is* the "narrow-only at every hop"
> rule, enforced statically at compile time rather than per-token at runtime.

### 2. Static, graph-level verification of attenuation is the live frontier

- **[MED]** "Formal Analysis and Supply Chain Security for Agentic AI Skills"
  claims a *compile-time* guarantee via abstract interpretation over a Dolev–Yao
  model: if static analysis on the skill manifest reports no violation, no
  operation exceeds its declared capability level, with non-amplification-under-
  composition theorems. *arXiv:2603.00195 — single-author preprint, proofs in
  unrendered appendices; treat theorems as unverified.*
- **[HIGH]** Agentproof statically verifies agent **workflow graphs** before
  execution: a graph × DFA product proves temporal/topology properties for all
  paths, sub-second up to ~5,000 nodes across LangGraph/CrewAI/AutoGen/ADK.
  *arXiv:2603.20356.*
- **[MED]** Agentproof operationalizes POLA at the *topology* level via a
  "human-gate coverage" check (every path to a sensitive tool passes a human
  gate) — but does not frame this as capability attenuation. *arXiv:2603.20356;
  the POLA connection is the analyst's, mechanism evaluated on 18 author-built
  workflows.*

> **Maps to Vaked.** This is exactly Vaked's bet: do the check at *compile time*
> over the declared graph, emit artifacts only if it passes. The literature is
> moving from runtime token checks toward the static, graph-level posture the
> compiler already takes.

### 3. MCP authorization is a hardened OAuth 2.1 design — on paper

- **[HIGH]** MCP servers are OAuth 2.1 **resource servers**; the 2025-06-18 spec
  revision (carried into 2025-11-25) **mandates audience-bound tokens** and
  **forbids token passthrough** (a server MUST reject tokens not issued for it
  and MUST NOT forward client tokens upstream). *modelcontextprotocol.io
  authorization spec; auth0.com/blog.*
- **[HIGH]** Clients MUST send **RFC 8707 Resource Indicators**, PKCE (S256) is
  mandatory, implicit grant dropped, redirect URIs exact-matched, auth-server
  location advertised via RFC 9728. *modelcontextprotocol.io authorization spec.*
- **[HIGH]** The spec endorses **least-privilege / step-up scoping** (request
  scopes incrementally via `WWW-Authenticate` 403 challenges) and names the
  anti-pattern: wildcard/omnibus scopes (`*`, `full-access`). *Caveat: default
  client fallback when no challenge scope is given is to request ALL supported
  scopes — least-privilege depends on servers emitting narrow challenges.*
  *modelcontextprotocol.io authorization + security best practices.*

> **Maps to Vaked.** The broker (`mcp.github_write`) is the single MCP-scoped
> writer. The spec's "narrow, audience-bound, no passthrough" lines up with the
> graph giving exactly one node that grant and no other.

### 4. The sole-publisher / single-writer broker is the literature's backbone defense

- **[HIGH]** The unifying principle: once an agent ingests untrusted input, it
  must be impossible for that input to trigger consequential actions — a hard
  architectural split between *read-untrusted* and *write/act*. *arXiv:2506.08837
  "Design Patterns for Securing LLM Agents"; Willison 2025-06-13.*
- **[HIGH]** Across the six named patterns (Action-Selector, Plan-Then-Execute,
  Dual-LLM, Code-Then-Execute, Map-Reduce, Context-Minimization), **exactly one
  component holds side-effect authority** and untrusted tokens never reach it —
  this is why a single-writer broker shrinks attack surface. *arXiv:2506.08837.*
- **[HIGH]** Gating the **egress/publish** leg defeats data theft: remove one leg
  of the "lethal trifecta" (private data + untrusted content + external comms) and
  injection becomes harmless because there is no exfiltration channel. *Willison
  2025-06-16, "The lethal trifecta".*
- **[HIGH]** CaMeL is the most rigorous instance: a privileged planner + a
  quarantined LLM, with a restricted interpreter tracking per-value capabilities
  so tainted data cannot flow into a sensitive sink without policy approval —
  ~77% AgentDojo utility *with provable security* vs 84% undefended (~7-pt cost).
  *arXiv:2503.18813; Willison 2025-04-11.*

> **Maps to Vaked.** The dogfood broker is precisely the "single component with
> side-effect authority"; the author/reviewer hold `fs.*` but never the publish
> grant. Pairing this with `agent_guardd`'s deny-by-default egress membrane gates
> the trifecta's third leg at the network layer.

### 5. The failure modes the design must answer

- **[HIGH]** **Excessive Agency (OWASP LLM06:2025):** today's default is a single
  principal with full access to all tools — a compromised agent can invoke
  anything. This is the gap POLA closes. *OWASP LLM06; arXiv:2503.15547.*
- **[HIGH]** **Confused deputy (MCP):** a proxy server with a static upstream
  `client_id` + dynamic registration + a consent cookie lets an attacker skip
  consent and redirect a victim's auth code. Fix: per-client consent before
  forwarding, exact redirect matching, single-use state. *modelcontextprotocol.io
  security best practices; flowhunt.io.*
- **[HIGH]** **Tool poisoning** (malicious instructions in tool metadata injected
  into context) is independently ranked the top client-side MCP vulnerability.
  *arXiv:2603.22489; descope.com 2026-01-26; OWASP.*
- **[HIGH]** **Privilege escalation via prompt injection — real incident:**
  June 2025, a Cursor agent with privileged service-role DB access processed
  attacker-controlled support tickets and was induced via embedded SQL to
  exfiltrate tokens to a public thread — the recurring triad of privileged
  access + untrusted input + an external channel. *securityboulevard.com.*
- **[MED-HIGH]** **Scope creep (OWASP MCP02:2025):** narrow grants drift into
  admin privilege over time; controls = fine-grained scopes, policy-as-code,
  JIT/time-limited access, separating grant-authority from deploy-authority.
  *owasp.org/www-project-mcp-top-10.*

## Disagreements / caveats

- **Where attenuation is enforced** splits three ways: cryptographic tokens
  (AIP/macaroons), static code/graph analysis (skills paper, Agentproof), and
  dynamic context-aware reasoning (Agent Access Control, arXiv:2510.11108) — AAC
  explicitly rejects the binary/static model and *omits delegation entirely*. A
  genuine architectural disagreement. Vaked sits firmly in the static-graph camp.
- **Spec vs. practice:** the MCP MUSTs (audience validation, resource indicators,
  per-client consent) are widely reported as **under-implemented** in shipping
  servers, so real-world posture depends on enforcement (gateways, policy-as-code,
  per-agent identity), not spec text. *flowhunt.io; arXiv:2603.22489 — MED, a
  vendor-blog prevalence assertion, not a measured study.*
- **Single-source / preprint risk:** claims 1–2 lean on two single-author 2026
  preprints (Prakash, Bhardwaj). The *properties* (subset/intersection, monotone
  narrowing) are mutually corroborating textbook ocap; the specific theorems and
  "100% rejection / 2.35ms overhead" benchmarks are unreplicated.

## Bottom line for the dogfood

The PR's authority graph is **well-aligned with 2025–2026 best practice and, on
the static-verification axis, slightly ahead of it.** Attenuation-only delegation
(narrow at every hop), a single side-effect-bearing broker, and gating the egress
leg are the three load-bearing recommendations across the strongest sources —
and they are exactly what the `mesh` field + `E-CAP-ATTENUATION` + the sole
`mcp.github_write` broker encode. The honest gaps the design should keep in view:
(a) the static check assumes the broker node itself is sound — defense-in-depth
still wants `agent_guardd`'s egress membrane; (b) prompt-injection / tool-
poisoning live at the model-context layer that capability graphs do not address,
so the graph confines *consequences*, not *compliance*.

## Sources

- IETF draft-prakash-aip-00 — https://www.ietf.org/archive/id/draft-prakash-aip-00.html
- AIP: Agent Identity Protocol — https://arxiv.org/abs/2603.24775
- Formal Analysis & Supply Chain Security for Agentic AI Skills — https://arxiv.org/pdf/2603.00195
- Agentproof: Static Verification of Agent Workflow Graphs — https://arxiv.org/html/2603.20356v1
- Workload-Router-Pool / vLLM Semantic Router — https://arxiv.org/pdf/2603.21354
- A Vision for Access Control in LLM-based Agent Systems — https://arxiv.org/abs/2510.11108
- MCP authorization spec — https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization
- MCP security best practices — https://modelcontextprotocol.io/specification/draft/basic/security_best_practices
- Auth0 — MCP specs update — https://auth0.com/blog/mcp-specs-update-all-about-auth/
- OWASP MCP Top 10 — MCP02 Privilege Escalation — https://owasp.org/www-project-mcp-top-10/2025/MCP02-2025%E2%80%93Privilege-Escalation-via-Scope-Creep
- MCP threat model (STRIDE/DREAD) — https://arxiv.org/abs/2603.22489
- Descope — MCP tool poisoning — https://www.descope.com/learn/post/mcp-tool-poisoning
- Defeating Prompt Injections by Design (CaMeL) — https://arxiv.org/pdf/2503.18813
- Design Patterns for Securing LLM Agents — https://arxiv.org/pdf/2506.08837
- Simon Willison — CaMeL — https://simonwillison.net/2025/Apr/11/camel/
- Simon Willison — design patterns — https://simonwillison.net/2025/Jun/13/prompt-injection-design-patterns/
- Simon Willison — the lethal trifecta — https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/
- OWASP LLM06:2025 Excessive Agency — https://www.a10networks.com/glossary/llm-excessive-agency/

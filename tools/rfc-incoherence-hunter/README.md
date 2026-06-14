# RFC Incoherence Hunter

Three-specialist multi-reasoner system that finds logical incoherence in the Vaked protocol RFC series. An orchestration expert, a kernel/eBPF contributor, and a theoretical CS / languages prodigy analyze RFC 0004 (agent orchestration) against RFC 0001–0003 in parallel, verify findings adversarially, and synthesize a coherence report.

## Architecture

- **Entry reasoner:** `rfc-incoherence-hunter.rfc_incoherence_hunter`
- **Pattern:** Parallel Hunters + HUNT→PROVE + Dynamic Cross-Reference Following
- **Reasoners (14 total):**
  - `section_classifier` — AI gate that assigns RFC sections to each specialist
  - `orchestration_expert` — orchestrates protocol-contract and lifecycle sub-checkers
  - `protocol_contract_checker` — finds missing preconditions, undefined error paths, round-trip gaps
  - `lifecycle_checker` — finds dead transitions, deadlocks, unreachable states
  - `kernel_expert` — orchestrates BPF-atomicity and thread-model sub-checkers
  - `bpf_atomicity_checker` — finds dual-writer risks, TID stability assumptions, map lifecycle gaps
  - `thread_model_checker` — finds BEAM/OS TID mismatch, TID reuse hazards, scheduler latency gaps
  - `languages_expert` — orchestrates formal-consistency and semantic-completeness sub-checkers
  - `formal_consistency_checker` — finds circular definitions, contradictory MUSTs, temporal violations
  - `semantic_completeness_checker` — finds undefined normative terms, unnamed reachable states
  - `cross_ref_follower` — conditionally follows cross-references from major/critical findings (depth-4)
  - `finding_verifier` — adversarial verifier that tries to REFUTE each non-minor finding
  - `coherence_report_composer` — synthesizes verified findings into a structured coherence report

## Run

```bash
cp .env.example .env
# edit .env — set OPENROUTER_API_KEY and confirm VAKED_REPO_PATH
docker compose up --build
```

Wait for `agent registered` in the logs (usually 10-20 seconds after control plane is healthy).

## Verify

Run in a second terminal after `docker compose up --build`:

```bash
# 1. Control plane up?
curl -fsS http://localhost:8080/api/v1/health | jq '.status'

# 2. Agent registered? (PRIMARY CHECK)
curl -fsS http://localhost:8080/api/v1/discovery/capabilities \
  | jq '.capabilities[] | select(.agent_id=="rfc-incoherence-hunter") | {
      agent_id,
      n_reasoners: (.reasoners | length),
      entry: [.reasoners[] | select(.tags[]? == "entry") | .id]
    }'

# 3. Run the incoherence hunt (async — pipeline takes 30-90s depending on model)
EXEC_ID=$(curl -sS -X POST \
  http://localhost:8080/api/v1/execute/async/rfc-incoherence-hunter.rfc_incoherence_hunter \
  -H 'Content-Type: application/json' \
  -d '{
    "input": {
      "model": "openrouter/google/gemini-2.5-flash"
    }
  }' | jq -r '.execution_id')
echo "Execution: $EXEC_ID"

# 4. Poll until done
while :; do
  R=$(curl -sS http://localhost:8080/api/v1/executions/$EXEC_ID)
  S=$(echo "$R" | jq -r '.status')
  case "$S" in
    succeeded) echo "$R" | jq '.result.report'; break ;;
    failed)    echo "$R" | jq '.'; break ;;
    *)         sleep 3 ;;
  esac
done

# 5. (Showpiece) verifiable credential chain — cryptographic proof of every reasoner that ran
LAST_WF=$(curl -s http://localhost:8080/api/v1/executions | jq -r '.[0].workflow_id')
curl -s http://localhost:8080/api/v1/did/workflow/$LAST_WF/vc-chain | jq
```

## Override the model per request

```bash
# Use a stronger model for deeper analysis
EXEC_ID=$(curl -sS -X POST \
  http://localhost:8080/api/v1/execute/async/rfc-incoherence-hunter.rfc_incoherence_hunter \
  -H 'Content-Type: application/json' \
  -d '{"input": {"model": "openrouter/anthropic/claude-3-5-sonnet-20241022"}}' \
  | jq -r '.execution_id')
```

## RFC volume

The container mounts `VAKED_REPO_PATH` (default: `/Users/lodripeter/workspace/peterlodri-sec/vaked-base`) as `/rfcs`. RFC files are read from `/rfcs/protocol/rfcs/*.md`. If the directory is empty, the agent returns an error with the path it looked in.

## Stop

```bash
docker compose down
docker compose down --volumes  # also clears control-plane state
```

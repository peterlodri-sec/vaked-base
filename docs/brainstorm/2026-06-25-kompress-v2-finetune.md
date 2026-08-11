# Kompress v2 Fine-tune Brainstorm
**chopratejas/kompress-v2-base — E2E with vaked/headroom/litellm/ultrawhale learnings**

Date: 2026-06-25  
Status: Draft / Exploratory

---

## What the model actually is

ModernBERT-base (`answerdotai/ModernBERT-base`, 768-dim hidden) with two custom heads trained via LoRA, merged into `merged.pt`:

**Head 1 — Token classifier (keep/discard)**
Linear(768, 2). Argmax decides keep vs discard. Token is "borderline" if softmax class-1 score is in [0.3, 0.5].

**Head 2 — Span importance (1D CNN)**
Conv1d(768→256, k=5) → GELU → Conv1d(256→1, k=3) → Sigmoid. Outputs per-token span score.

**Final decision**: keep = token_head_says_keep OR (borderline AND span_score > 0.5)

For ranking (target_ratio mode): final_score = token_prob * (0.5 + 0.5 * span_score)

**Current production metrics (dataset_v2 test, n=500):**
F1=0.913, must_keep_recall=0.977, keep_rate=0.810

**Key gap**: training data is generic "tool output" text. The model has no signal about:
- role context (tool_result vs assistant vs system)
- content type (shell output, JSON, code, prose, error traces)
- downstream trust level (agent vs human reader)

---

## Core learning: what breaks compression

From headroom contribution work (#1307, #1363, #1389):

**What the model should NEVER compress:**
- Exact-match content: file paths, line numbers, symbol names, CLI flags, exit codes
- Tool_result blocks when the agent will read them to verify facts (grep results, test output, ls output)
- Error traces — single corrupted line invalidates the whole trace
- JSON keys (values maybe, keys never)
- Code identifiers — compressing `setrlimit` to `set_rl` breaks everything

**What it's safe to compress:**
- Prose explanation wrapping a fact ("The function `foo` does X, Y, and Z. It was originally designed to..." → keep the fact, drop the narrative)
- Repeated boilerplate (import blocks, license headers, repeated log timestamps)
- Verbose assistant narration ("Now I will proceed to check..." type filler)

**Root cause of current failures**: the model learned "compression ratio" as a proxy for quality. It doesn't know that keeping 80% of a grep result at 100% accuracy is better than keeping 60% with one hallucinated match.

---

## Data strategy

### Source 1: ultrawhale dogfeed dataset
`PeetPedro/ultrawhale-dogfood` — 5k+ Q&A pairs, real LLM outputs across diverse topics.

Useful because: answers contain the exact mixture headroom sees — structured explanation, code snippets, references, prose.

**Annotation signal to extract:**
- Strip all filler sentences (define: sentence that adds no new fact vs the rest of the answer)
- Create (original, compressed, label_mask) triples where label_mask[i]=1 means token i is semantically load-bearing

### Source 2: headroom proxy logs (differential capture)
The mitmproxy capture in `headroom/docker/differential-network-capture/` captures real proxy traffic. From this:

- Extract (original_message, kompress_compressed) pairs
- Run a judge LLM (Qwen2.5-72B via HF inference or OpenRouter) asking "does the compressed version preserve all facts needed to continue the task?"
- Label = 1 (good keep) / 0 (bad compression) per token based on judge verdict + diff alignment

**Key insight from issue #1307**: when the agent says "the output looks mangled", that's a direct quality signal. Mine the Claude Code session logs for these patterns. Each "I'll re-read the file" after a tool call is a negative sample.

### Source 3: litellm proxy traffic patterns
From our litellm contribution work, the proxy handles:
- Anthropic `/v1/messages` with structured content blocks
- Tool_use / tool_result blocks
- System prompts with cache_control markers

The content that flows through has known structure. Build role-aware training pairs:
- `role=tool` content → stricter keep threshold, higher must-keep for non-prose tokens
- `role=system` → very conservative, these get cached, compression breaks prefix stability
- `role=assistant` prose → aggressive, keep only factual claims

### Source 4: vaked infrastructure knowledge
From NixOS hardening / Caddy config work: technical operational content (systemd unit files, nix expressions, YAML configs) is a category the model hasn't seen much. These are tool outputs in real agent loops.

Collect Caddy error logs, nix evaluation traces, docker-compose output as domain-specific training samples.

---

## Architecture changes for fine-tune

### Option A: LoRA re-tune (cheapest, lowest risk)
Keep the ModernBERT encoder frozen. Re-tune only Head 1 + Head 2 + small LoRA rank on the encoder last 4 layers.

**Why this works**: the encoder already knows language; the heads learned the wrong objective (ratio optimization vs task-completion preservation).

```python
# LoRA config estimate
lora_config = LoraConfig(
    r=16,
    lora_alpha=32,
    target_modules=["query", "key", "value"],
    lora_dropout=0.05,
    layers_to_transform=list(range(18, 22)),  # last 4 of 22 ModernBERT layers
)
```

### Option B: Role-conditioned scoring (higher impact, more work)
Add a role embedding (4-class: system, user, assistant, tool) injected at the encoder's first layer. The keep threshold varies by role at inference time.

Inference change: KompressCompressor receives `role` → uses role-specific threshold (e.g. tool=0.6, assistant=0.45, system=0.7).

This directly addresses the root cause of issue #1307 without the `none` profile workaround.

### Option C: Content-type routing (most ambitious)
Add a content-type classifier head (prose, code, json, shell_output, error_trace) that routes to specialized keep policies.

- shell_output: very high threshold on line-start tokens (paths, numbers, keywords), low on repetitive timestamps
- json: keep all keys, compress repetitive values by semantic similarity
- error_trace: keep all non-whitespace tokens up to the first "at" line, then compress later frames

This is architecturally a multi-task model. LoRA adapters per content type, routed by content-type head.

---

## Training objective

Current: binary cross-entropy on keep/discard labels.

**Better objective**: weighted BCE where weight = semantic importance of token to task completion.

Concretely:
```
loss = BCE(pred, label) * importance_weight
importance_weight[i] = 1.0  # default
importance_weight[i] = 3.0  # if token is a number, identifier, path, or code token
importance_weight[i] = 5.0  # if token appears in a must-keep span (verified by judge)
importance_weight[i] = 0.3  # if token is punctuation / article / preposition
```

**Contrastive component**: add a term that penalizes cases where the model keeps `p% of tokens but the agent still fails` vs `q% with task success` — train the model to maximize task-completion given budget, not compression ratio.

---

## MLX local training on M3 (from blogpost learnings)

From the M3 dogfeed post: Qwen2.5-14B-4bit fits in 16GB. ModernBERT-base is 140M params — trivially fits.

```bash
# Fine-tune on M3 Pro with MLX
pip install mlx mlx-lm
# Convert to MLX
python -m mlx_lm.convert --hf-path answerdotai/ModernBERT-base --mlx-path ./modernbert-mlx

# But: custom dual-head architecture won't work with mlx_lm directly
# Need custom MLX training loop
```

Realistic path: run the LoRA fine-tune on M3 with PyTorch MPS backend (not MLX, since the architecture is custom).

```python
device = torch.device("mps")
model.to(device)
optimizer = torch.optim.AdamW(lora_params, lr=2e-4)
```

With the 5k ultrawhale pairs + ~2k headroom proxy samples: ~3-4 hours on M3 Pro for 3 epochs.

---

## Evaluation metrics that actually matter

Current metrics are model-centric (F1 on label set). Need task-centric evaluation:

1. **Agent task completion rate**: run Claude Code / Codex on a fixed set of tasks with headroom proxy using original Kompress vs fine-tuned. Measure: tasks completed without "I'll re-read this" backtrack.

2. **Semantic drift score**: cosine similarity between original and compressed using a small embedding model (e.g. bge-small-en-v1.5). Must stay > 0.85 per chunk.

3. **Exact-match preservation**: for tool_result content, what % of numbers, paths, and identifiers survive unchanged?

4. **Keep rate at quality target**: at semantic_drift > 0.85 and exact_match > 0.95, what's the achieved keep_rate? Lower is better (more compression while staying above quality floor).

The goal is NOT to push F1 higher — it's to push keep_rate down while keeping task_completion_rate constant. That's the actual value proposition.

---

## Data pipeline (concrete steps)

```
1. Export ultrawhale dataset
   ultrawhale-export: uv run python scripts/export_for_kompress.py
   output: data/kompress_train_raw.jsonl
   format: {text, role, content_type, source}

2. Auto-annotate with judge LLM
   for each record: ask Qwen2.5-72B (HF inference):
     "Which sentences/tokens carry factual claims the reader needs? Mark them."
   output: data/kompress_train_annotated.jsonl
   format: {text, token_labels, must_keep_spans, role, content_type}

3. Headroom proxy differential pairs
   run headroom proxy in capture mode on agent sessions
   collect (original, compressed) pairs
   judge: does compressed preserve all facts for task continuation?
   output: data/kompress_proxy_pairs.jsonl

4. Balance and split
   total: ~7k samples
   split: 80/10/10 train/val/test
   balance: ensure 30% tool_result, 30% assistant prose, 20% code, 20% other

5. Fine-tune
   architecture: LoRA(r=16) on last 4 layers + heads
   epochs: 3, batch_size: 16, lr: 2e-4 with cosine decay
   loss: weighted BCE + contrastive term
   hardware: M3 Pro, MPS backend, ~4h

6. ONNX export
   python scripts/export_kompress_v2_onnx.py \
     --model-id ./finetuned-kompress-v3 \
     --upload  # → chopratejas/kompress-v3-vaked OR peterlodri-sec/kompress-v3

7. Eval on headroom agent-evals suite
   pytest headroom/agent-evals/
   target: keep_rate < 0.75 at semantic_drift > 0.85
```

---

## What to call it

**kompress-v3-vaked** — signals domain: agent loop traffic, vaked-style tool outputs, headroom-hardened.

Or contribute back: open a PR to chopratejas/kompress-v2-base with the improved checkpoint. Given our headroom contributions, this is credible.

---

## Risks

1. **Judge LLM cost**: annotating 7k samples with Qwen2.5-72B via HF Pro: ~$2-3 if batched. Cheap.
2. **ModernBERT weights change**: if `answerdotai/ModernBERT-base` updates, the base embeddings shift. Pin the version.
3. **ONNX export of custom heads**: the export script already handles the dual-head custom architecture. LoRA merging must happen before export.
4. **Headroom proxy data sensitivity**: proxy traffic may contain PII. The PII scrubber from dogfeedOS (`_PII` regex list) applies here too. Strip before export to HF.
5. **Distribution shift**: ultrawhale data is Q&A prose. Real tool outputs are different. Need the headroom proxy pairs to compensate.

---

## Next concrete step

Build the export script first — take ultrawhale dataset → (text, role) pairs → auto-annotate with a simple heuristic (number/path/identifier = must_keep, filler words = discard). No LLM judge needed for the first iteration. Run LoRA fine-tune. Eval on keep_rate. Then iterate with judge labels if the first pass shows promise.

`ultrawhale/scripts/export_for_kompress.py` → Taskfile target → `task kompress-data`

---

## Addendum: Unsloth + LLM-based compression (kompress-v4 concept)

Unsloth's CUDA kernels don't apply to ModernBERT (bidirectional encoder). But Unsloth excels at fine-tuning small decoder LLMs. This opens a second compression path:

**Qwen2.5-0.5B fine-tuned with Unsloth as a text-to-text compressor:**

```python
from unsloth import FastLanguageModel
model, tokenizer = FastLanguageModel.from_pretrained(
    "unsloth/Qwen2.5-0.5B-Instruct-bnb-4bit",
    max_seq_length=1024,
    load_in_4bit=True,
)
model = FastLanguageModel.get_peft_model(model, r=16, target_modules=["q_proj","v_proj"])
```

Training prompt:
```
[COMPRESS] {deepseek_response}
### Compressed:
{free_response}
```

6 minutes on RTX 4090. $0.04.

**When to use which:**
- Kompress (token-deletion): tool_result, JSON, code, grep output — structure matters, must not hallucinate
- Qwen compressor (regenerative): long assistant prose, explanations, analysis — can rephrase, OK to summarize

Two-path compression is what headroom v3 should ship.

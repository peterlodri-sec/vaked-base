package llm

import (
	"encoding/json"
	"fmt"

	"github.com/cloudwego/eino/schema"
	"github.com/eino-contrib/jsonschema"

	"github.com/peterlodri-sec/vaked-base/tools/optitron/internal/gate"
)

// The four strict OpenRouter json_schema response formats. Every field is
// required and additionalProperties is false, so a lenient provider can't omit a
// field and slip past the gate. These mirror optitroncore.py's schemas verbatim.

const crawlSchemaJSON = `{
  "type":"object","additionalProperties":false,"required":["candidates"],
  "properties":{"candidates":{"type":"array","items":{
    "type":"object","additionalProperties":false,
    "required":["title","area","mechanism","claim","sources","signature"],
    "properties":{
      "title":{"type":"string"},
      "area":{"type":"string","enum":["compiler","allocator","zig","rust","vaked"]},
      "mechanism":{"type":"string"},
      "claim":{"type":"string"},
      "sources":{"type":"array","items":{
        "type":"object","additionalProperties":false,
        "required":["url","kind","org","quote"],
        "properties":{"url":{"type":"string"},"kind":{"type":"string"},
          "org":{"type":"string"},"quote":{"type":"string"}}}},
      "signature":{"type":"string"}}}}}}`

const verifySchemaJSON = `{
  "type":"object","additionalProperties":false,
  "required":["independent","independent_count","rationale","claim_supported","caveats"],
  "properties":{
    "independent":{"type":"boolean"},
    "independent_count":{"type":"integer"},
    "rationale":{"type":"string"},
    "claim_supported":{"type":"boolean"},
    "caveats":{"type":"string"}}}`

const benchSchemaJSON = `{
  "type":"object","additionalProperties":false,
  "required":["lang","source","notes"],
  "properties":{
    "lang":{"type":"string","enum":["rust","c"]},
    "source":{"type":"string"},
    "notes":{"type":"string"}}}`

const adjudicateSchemaJSON = `{
  "type":"object","additionalProperties":false,
  "required":["confidence","novel","hallucination_risk","verdict"],
  "properties":{
    "confidence":{"type":"number"},
    "novel":{"type":"boolean"},
    "hallucination_risk":{"type":"string","enum":["low","medium","high"]},
    "verdict":{"type":"string"}}}`

// mustSchema parses a raw JSON schema into eino's jsonschema.Schema (verified to
// round-trip cleanly). Panics on a malformed literal — a programming error.
func mustSchema(raw string) *jsonschema.Schema {
	var s jsonschema.Schema
	if err := json.Unmarshal([]byte(raw), &s); err != nil {
		panic(fmt.Sprintf("optitron: bad embedded schema: %v", err))
	}
	return &s
}

// Schema names + parsed schemas for each pipeline leg.
var (
	CrawlSchema      = &NamedSchema{"optitron_candidates", mustSchema(crawlSchemaJSON)}
	VerifySchema     = &NamedSchema{"optitron_verify", mustSchema(verifySchemaJSON)}
	BenchSchema      = &NamedSchema{"optitron_bench", mustSchema(benchSchemaJSON)}
	AdjudicateSchema = &NamedSchema{"optitron_adjudicate", mustSchema(adjudicateSchemaJSON)}
)

// NamedSchema is a named, strict json_schema response format. Exported so sibling
// agents in this module (e.g. cmd/introspect) can define their own schemas and
// drive Client.CallJSON with them.
type NamedSchema struct {
	Name   string
	Schema *jsonschema.Schema
}

// NewSchema builds a NamedSchema from a raw JSON-schema literal (panics on a
// malformed literal — a programming error, surfaced at startup).
func NewSchema(name, rawJSON string) *NamedSchema {
	return &NamedSchema{Name: name, Schema: mustSchema(rawJSON)}
}

// --- Prompt builders. The crawl prompt embeds SKILL.md as the system message,
// so the harness is a faithful projection of the declarative skill. Ported from
// optitroncore.build_* ---

func sys(skill string) *schema.Message { return schema.SystemMessage(skill) }

// BuildCrawlMessages asks for in-scope candidates with real, quoted sources for
// ONE source family. The pipeline fans these out concurrently across families.
func BuildCrawlMessages(skill, purpose, sourcesHint string, priorTitles []string) []*schema.Message {
	prior := "(none yet)"
	if n := len(priorTitles); n > 0 {
		if n > 40 {
			priorTitles = priorTitles[n-40:]
		}
		prior = ""
		for _, t := range priorTitles {
			prior += "- " + t + "\n"
		}
	}
	user := fmt.Sprintf(`%s

CRAWL these source families for RECENT, in-scope candidate optimizations (compiler | allocator | zig | rust | vaked):
%s

For each candidate give the concrete mechanism, the measurable claim, and >=2 sources with EXACT supporting quotes + the publishing org (for an independence check). Provide a grep-able `+"`signature`"+` that would appear in a codebase that ALREADY applies it (used to reject non-novel finds).

Do NOT invent sources or quotes. If you cannot find a real, recent, in-scope optimization with real sources, return an EMPTY candidates array.

Already-found (do not repeat):
%s`, purpose, sourcesHint, prior)
	return []*schema.Message{sys(skill), schema.UserMessage(user)}
}

// BuildVerifyMessages drives the skeptical Reasoner cross-check.
func BuildVerifyMessages(skill string, c gate.Candidate) []*schema.Message {
	b, _ := json.MarshalIndent(c, "", "  ")
	user := "Adversarially CROSS-CHECK this candidate. Decide `independent`: are there " +
		">=2 authoritative sources from DISTINCT origins (different orgs/domains) that each " +
		"independently support the claim — NOT a citation chain where one merely cites another? " +
		"Count them. Confirm the exact quotes actually support the claim. Be skeptical; a " +
		"plausible-sounding but unsourced mechanism is a hallucination.\n\nCANDIDATE:\n" + string(b)
	return []*schema.Message{sys(skill), schema.UserMessage(user)}
}

// BuildBenchMessages drives the Generator to emit a self-contained micro-bench.
func BuildBenchMessages(skill string, c gate.Candidate) []*schema.Message {
	b, _ := json.MarshalIndent(c, "", "  ")
	user := "Write ONE self-contained micro-benchmark that demonstrates this optimization versus " +
		"its baseline. Constraints: single file; no external crates/deps; deterministic; runs in " +
		"< 20s; uses a monotonic clock. It MUST print exactly one line to stdout:\n" +
		"    OPTITRON_BENCH baseline=<ns> optimized=<ns>\n" +
		"where the two values are nanoseconds for the baseline vs optimized variant of the SAME " +
		"workload. No other stdout. lang is `rust` (compiled with `rustc -O`) or `c` (compiled " +
		"with `cc -O2`).\n\nCANDIDATE:\n" + string(b)
	return []*schema.Message{sys(skill), schema.UserMessage(user)}
}

// BuildAdjudicateMessages drives the final Reasoner certainty score.
func BuildAdjudicateMessages(skill string, c gate.Candidate, v gate.Verify, bench *gate.BenchResult) []*schema.Message {
	cb, _ := json.MarshalIndent(c, "", "  ")
	vb, _ := json.MarshalIndent(v, "", "  ")
	var bb []byte
	if bench != nil {
		bb, _ = json.MarshalIndent(bench, "", "  ")
	} else {
		bb = []byte("null")
	}
	user := "Final adjudication. Given the candidate, the cross-check verdict, and the MEASURED " +
		"benchmark result, output your internal certainty (`confidence` 0..1) that this is a REAL, " +
		"NOVEL optimization — not a hallucination. Be conservative: reserve confidence >= 0.8 for " +
		"findings with independent sources AND a real measured improvement. Anything speculative " +
		"scores low.\n\nCANDIDATE:\n" + string(cb) + "\n\nCROSS-CHECK:\n" + string(vb) + "\n\nBENCH:\n" + string(bb)
	return []*schema.Message{sys(skill), schema.UserMessage(user)}
}

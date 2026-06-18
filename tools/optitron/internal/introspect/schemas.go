package introspect
import (
	"encoding/json"
	"github.com/cloudwego/eino/schema"
	"github.com/peterlodri-sec/vaked-base/tools/optitron/internal/llm"
)
type Finding struct {
	Finding   string `json:"finding"`
	Bot       string `json:"bot"`
	Evidence  string `json:"evidence"`
	Severity  string `json:"severity"`
	Rationale string `json:"rationale"`
}
type Idea struct {
	Title            string   `json:"title"`
	Mechanism        string   `json:"mechanism"`
	NoveltyRationale string   `json:"novelty_rationale"`
	TargetFiles      []string `json:"target_files"`
	ExpectedEffect   string   `json:"expected_effect"`
	Evidence         string   `json:"evidence"`
	Signature        string   `json:"signature"`
	Confidence       float64  `json:"confidence"`
}
type Review struct {
	Approved   bool    `json:"approved"`
	Novel      bool    `json:"novel"`
	Grounded   bool    `json:"grounded"`
	Actionable bool    `json:"actionable"`
	Confidence float64 `json:"confidence"`
	Critique   string  `json:"critique"`
}
var (
	DetectSchema = llm.NewSchema("introspect_detect", `{
      "type":"object","additionalProperties":false,
      "required":["finding","bot","evidence","severity","rationale"],
      "properties":{
        "finding":{"type":"string"},"bot":{"type":"string"},
        "evidence":{"type":"string"},
        "severity":{"type":"string","enum":["low","medium","high"]},
        "rationale":{"type":"string"}}}`)
	IdeateSchema = llm.NewSchema("introspect_idea", `{
      "type":"object","additionalProperties":false,
      "required":["title","mechanism","novelty_rationale","target_files","expected_effect","evidence","signature","confidence"],
      "properties":{
        "title":{"type":"string"},"mechanism":{"type":"string"},
        "novelty_rationale":{"type":"string"},
        "target_files":{"type":"array","items":{"type":"string"}},
        "expected_effect":{"type":"string"},"evidence":{"type":"string"},
        "signature":{"type":"string"},"confidence":{"type":"number"}}}`)
	ReviewSchema = llm.NewSchema("introspect_review", `{
      "type":"object","additionalProperties":false,
      "required":["approved","novel","grounded","actionable","confidence","critique"],
      "properties":{
        "approved":{"type":"boolean"},"novel":{"type":"boolean"},
        "grounded":{"type":"boolean"},"actionable":{"type":"boolean"},
        "confidence":{"type":"number"},"critique":{"type":"string"}}}`)
)
func sys(purpose string) *schema.Message { return schema.SystemMessage(purpose) }
func DetectMessages(purpose, digest, focus string) []*schema.Message {
	user := "Below is the fleet's own telemetry digest (Langfuse traces + ledgers + CI) for the " +
		"recent window. Identify the SINGLE most salient finding worth improving — an error/retry " +
		"spike, a latency or cost outlier, truncation, a low ratify-rate, or a repeated failure. " +
		"Ground it in EXACT numbers from the digest; do not invent any. Output one finding.\n\n"
	if focus != "" {
		user += "OPERATOR FOCUS (prioritise this if the digest supports it): " + focus + "\n\n"
	}
	user += "DIGEST:\n" + digest
	return []*schema.Message{sys(purpose), schema.UserMessage(user)}
}
func IdeateMessages(purpose string, finding Finding, digest string) []*schema.Message {
	fb, _ := json.MarshalIndent(finding, "", "  ")
	user := "Design ONE novel, concrete solution/idea for the finding below. It must be actionable " +
		"in THIS repo (name target files), grounded in the telemetry numbers (quote them in " +
		"`evidence`), and genuinely novel — not already common practice or already applied here. " +
		"Provide a grep-able `signature` that would appear in a codebase that ALREADY does it. Be " +
		"honest about `confidence`.\n\nFINDING:\n" + string(fb) + "\n\nDIGEST (for grounding):\n" + digest
	return []*schema.Message{sys(purpose), schema.UserMessage(user)}
}
func ReviewMessages(purpose string, finding Finding, idea Idea, digest string) []*schema.Message {
	fb, _ := json.MarshalIndent(finding, "", "  ")
	ib, _ := json.MarshalIndent(idea, "", "  ")
	user := "Adversarially REVIEW this proposed idea before it is filed. Decide: is it `novel` (not " +
		"already in the repo/ledger, not generic advice), `grounded` (its evidence cites REAL numbers " +
		"present in the digest, not hallucinated), and `actionable` (concrete, scoped, names plausible " +
		"target files)? Set `approved` only if all hold. Be skeptical — a plausible-sounding but " +
		"ungrounded idea is a hallucination and must be rejected.\n\nFINDING:\n" + string(fb) +
		"\n\nIDEA:\n" + string(ib) + "\n\nDIGEST (the ground truth):\n" + digest
	return []*schema.Message{sys(purpose), schema.UserMessage(user)}
}
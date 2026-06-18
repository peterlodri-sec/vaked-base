package introspect
import (
	"math"
	"testing"
)
func approx(a, b float64) bool { return math.Abs(a-b) < 1e-6 }
func TestAggregateByModelClientSideCost(t *testing.T) {
	obs := []map[string]any{
		{"model": "deepseek/deepseek-v4-flash", "promptTokens": float64(1000), "completionTokens": float64(500), "latency": 1.0, "level": "DEFAULT"},
		{"model": "deepseek/deepseek-v4-flash", "promptTokens": float64(1000), "completionTokens": float64(500), "latency": 3.0, "statusMessage": "boom"},
		{"model": "anthropic/claude-opus-4.8", "usage": map[string]any{"input": float64(2000), "output": float64(1000)}, "latency": 2.0, "finishReason": "length"},
	}
	cost := func(_ string, pin, pout int) float64 { return float64(pin)/1e6*1.0 + float64(pout)/1e6*2.0 }
	by := AggregateByModel(obs, cost)
	ds := by["deepseek/deepseek-v4-flash"]
	if ds.Calls != 2 || ds.Errors != 1 {
		t.Fatalf("deepseek: calls=%d errors=%d", ds.Calls, ds.Errors)
	}
	if ds.PromptTokens != 2000 || ds.CompletionTokens != 1000 {
		t.Fatalf("deepseek tokens: %d/%d", ds.PromptTokens, ds.CompletionTokens)
	}
	if !approx(ds.Cost, 0.004) { // 2*(1000*1 + 500*2)/1e6
		t.Fatalf("deepseek cost = %v, want 0.004", ds.Cost)
	}
	op := by["anthropic/claude-opus-4.8"]
	if op.Truncated != 1 || op.PromptTokens != 2000 {
		t.Fatalf("opus: trunc=%d pin=%d", op.Truncated, op.PromptTokens)
	}
}
func TestSpanCounts(t *testing.T) {
	c := SpanCounts([]map[string]any{{"name": "gen_ai.generate"}, {"name": "gen_ai.generate"}, {"name": "pr_review"}})
	if c["gen_ai.generate"] != 2 || c["pr_review"] != 1 {
		t.Fatalf("span counts: %v", c)
	}
}
func TestProjectLinear(t *testing.T) {
	e := Project(0.34, 2.0)
	if !approx(e.PerDay, 0.17) {
		t.Fatalf("per_day = %v", e.PerDay)
	}
	if !approx(e.PerWeek, round(0.17*7, 2)) || !approx(e.PerMonth, round(0.17*30.4, 2)) {
		t.Fatalf("week/month = %v/%v", e.PerWeek, e.PerMonth)
	}
}
func TestBuildDigestEconomy(t *testing.T) {
	by := map[string]*ModelStats{"m": {Calls: 1, Cost: 1.0, PromptTokens: 10, CompletionTokens: 5}}
	md, econ := BuildDigest(by, map[string]int{"m": 1}, map[string]any{"ralph": map[string]any{"events": 0}}, nil, 2.0)
	if !approx(econ.WindowCost, 1.0) || !approx(econ.PerDay, 0.5) {
		t.Fatalf("econ = %+v", econ)
	}
	if len(md) == 0 {
		t.Fatal("empty digest")
	}
}
func TestPassesGate(t *testing.T) {
	ok := Review{Approved: true, Novel: true, Grounded: true, Actionable: true, Confidence: 0.9}
	if p, r := PassesGate(ok, 0.75); !p || r != "" {
		t.Fatalf("strong review should pass, got %v %q", p, r)
	}
	cases := []struct {
		r    Review
		want string
	}{
		{Review{Novel: true, Grounded: true, Actionable: true, Confidence: 0.9}, "not-approved"},
		{Review{Approved: true, Grounded: true, Actionable: true, Confidence: 0.9}, "not-novel"},
		{Review{Approved: true, Novel: true, Actionable: true, Confidence: 0.9}, "not-grounded-in-telemetry"},
		{Review{Approved: true, Novel: true, Grounded: true, Confidence: 0.9}, "not-actionable"},
		{Review{Approved: true, Novel: true, Grounded: true, Actionable: true, Confidence: 0.5}, "below-confidence-threshold"},
	}
	for _, c := range cases {
		if p, r := PassesGate(c.r, 0.75); p || r != c.want {
			t.Fatalf("want reject %q, got p=%v r=%q", c.want, p, r)
		}
	}
}
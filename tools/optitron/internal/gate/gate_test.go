package gate
import "testing"
func TestInScope(t *testing.T) {
	for _, s := range []string{"compiler", "Rust allocator", "Zig codegen"} {
		if !InScope(s) {
			t.Errorf("%q should be in scope", s)
		}
	}
	if InScope("javascript bundler") {
		t.Error("out-of-scope text matched")
	}
}
func TestSourcesIndependent(t *testing.T) {
	indep := []Source{
		{URL: "https://arxiv.org/abs/1234", Org: "MIT"},
		{URL: "https://llvm.org/notes", Org: "LLVM"},
	}
	if !SourcesIndependent(indep, 2) {
		t.Error("distinct domains+orgs should be independent")
	}
	chain := []Source{
		{URL: "https://blog.example.com/a", Org: "Example"},
		{URL: "https://blog.example.com/b", Org: "Example"},
	}
	if SourcesIndependent(chain, 2) {
		t.Error("same domain/org must fail independence")
	}
}
func TestParseBenchOutput(t *testing.T) {
	res, ok := ParseBenchOutput("noise\nOPTITRON_BENCH baseline=100 optimized=80\nmore")
	if !ok {
		t.Fatal("sentinel should parse")
	}
	if res.Delta < 0.19 || res.Delta > 0.21 {
		t.Errorf("delta = %v, want ~0.20", res.Delta)
	}
	if _, ok := ParseBenchOutput("no sentinel here"); ok {
		t.Error("missing sentinel must fail")
	}
	if _, ok := ParseBenchOutput("OPTITRON_BENCH baseline=0 optimized=0"); ok {
		t.Error("non-positive baseline must fail")
	}
}
func TestPassesGate(t *testing.T) {
	good := Verify{Independent: true, IndependentCount: 2, ClaimSupported: true}
	bench := &BenchResult{Delta: 0.15}
	adj := Adjudication{Confidence: 0.9, Novel: true, HallucinationRisk: "low"}
	if ok, reason := PassesGate(good, bench, adj, 2, 0.80, 0.10); !ok {
		t.Fatalf("strong finding should pass, got %q", reason)
	}
	if ok, reason := PassesGate(good, &BenchResult{Delta: 0.05}, adj, 2, 0.80, 0.10); ok || reason != "benchmark-missing-or-below-threshold" {
		t.Fatalf("low delta should reject, got ok=%v reason=%q", ok, reason)
	}
	if ok, _ := PassesGate(good, nil, adj, 2, 0.80, 0.10); ok {
		t.Fatal("nil bench must reject")
	}
	if ok, reason := PassesGate(good, bench, Adjudication{Confidence: 0.5, Novel: true, HallucinationRisk: "low"}, 2, 0.80, 0.10); ok || reason != "below-confidence-threshold" {
		t.Fatalf("low confidence should reject, got ok=%v reason=%q", ok, reason)
	}
}
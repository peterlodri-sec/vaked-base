// Package gate is the deterministic, side-effect-free heart of optitron's
// anti-hallucination strategy: the in-scope filter, the source-independence
// check, the benchmark-sentinel parser, and the strict pass/reject gate. It is a
// faithful port of the pure logic in tools/optitron/optitroncore.py and is fully
// unit-testable offline.
//
// In the PentestGPT-inspired module split this package is the *Parser* leg: it
// turns model output + measured facts into a typed verdict, with no model in the
// loop.
package gate

import (
	"net/url"
	"regexp"
	"strconv"
	"strings"
)

// Scope — optitron only hunts in these domains. Anything else is discarded
// before any verification spend.
var Scope = []string{"compiler", "allocator", "zig", "rust", "vaked"}

// InScope reports whether text mentions any in-scope area.
func InScope(text string) bool {
	t := strings.ToLower(text)
	for _, k := range Scope {
		if strings.Contains(t, k) {
			return true
		}
	}
	return false
}

// Source is one piece of evidence for a candidate.
type Source struct {
	URL   string `json:"url"`
	Kind  string `json:"kind"`  // paper | release-note | upstream-rfc | benchmark
	Org   string `json:"org"`   // publishing org/author (for independence)
	Quote string `json:"quote"` // the exact supporting sentence
}

// Candidate is one crawled optimization claim.
type Candidate struct {
	Title     string   `json:"title"`
	Area      string   `json:"area"`
	Mechanism string   `json:"mechanism"`
	Claim     string   `json:"claim"`
	Sources   []Source `json:"sources"`
	Signature string   `json:"signature"` // grep-able marker if already applied
}

// Verify is the adversarial cross-check verdict.
type Verify struct {
	Independent      bool   `json:"independent"`
	IndependentCount int    `json:"independent_count"`
	Rationale        string `json:"rationale"`
	ClaimSupported   bool   `json:"claim_supported"`
	Caveats          string `json:"caveats"`
}

// BenchSpec is the model-authored micro-benchmark program.
type BenchSpec struct {
	Lang   string `json:"lang"` // rust | c
	Source string `json:"source"`
	Notes  string `json:"notes"`
}

// BenchResult is the measured outcome of compiling + running a BenchSpec.
type BenchResult struct {
	BaselineNs  float64 `json:"baseline_ns"`
	OptimizedNs float64 `json:"optimized_ns"`
	Delta       float64 `json:"delta"` // relative improvement (baseline-optimized)/baseline
}

// Adjudication is the final certainty scoring.
type Adjudication struct {
	Confidence        float64 `json:"confidence"`
	Novel             bool    `json:"novel"`
	HallucinationRisk string  `json:"hallucination_risk"` // low | medium | high
	Verdict           string  `json:"verdict"`
}

func registrableDomain(raw string) string {
	u, err := url.Parse(raw)
	if err != nil || u.Hostname() == "" {
		return ""
	}
	host := strings.ToLower(u.Hostname())
	parts := strings.Split(host, ".")
	if len(parts) >= 2 {
		return strings.Join(parts[len(parts)-2:], ".")
	}
	return host
}

// SourcesIndependent is true iff >= minSources come from DISTINCT registrable
// domains AND distinct orgs — defeating citation-chains/self-references that
// share a domain or author.
func SourcesIndependent(sources []Source, minSources int) bool {
	domains := map[string]struct{}{}
	orgs := map[string]struct{}{}
	for _, s := range sources {
		if d := registrableDomain(s.URL); d != "" {
			domains[d] = struct{}{}
		}
		if o := strings.ToLower(strings.TrimSpace(s.Org)); o != "" {
			orgs[o] = struct{}{}
		}
	}
	return len(domains) >= minSources && len(orgs) >= minSources
}

var benchRE = regexp.MustCompile(`OPTITRON_BENCH\s+baseline=([0-9.]+)\s+optimized=([0-9.]+)`)

// ParseBenchOutput extracts the sentinel line into a BenchResult. Returns
// (result, false) if the sentinel is absent, malformed, or non-positive.
func ParseBenchOutput(stdout string) (BenchResult, bool) {
	m := benchRE.FindStringSubmatch(stdout)
	if m == nil {
		return BenchResult{}, false
	}
	base, err1 := strconv.ParseFloat(m[1], 64)
	opt, err2 := strconv.ParseFloat(m[2], 64)
	if err1 != nil || err2 != nil || base <= 0 || opt < 0 {
		return BenchResult{}, false
	}
	return BenchResult{BaselineNs: base, OptimizedNs: opt, Delta: (base - opt) / base}, true
}

// PassesGate is the strict, fail-closed gate. It returns (false, reason) the
// moment any stage falls short, mirroring optitroncore.passes_gate.
func PassesGate(v Verify, bench *BenchResult, adj Adjudication, minSources int, minConfidence, minDelta float64) (bool, string) {
	if !v.Independent || v.IndependentCount < minSources {
		return false, "insufficient-independent-sources"
	}
	if !v.ClaimSupported {
		return false, "claim-not-supported"
	}
	if bench == nil || bench.Delta < minDelta {
		return false, "benchmark-missing-or-below-threshold"
	}
	if !adj.Novel {
		return false, "not-novel"
	}
	if adj.HallucinationRisk == "high" {
		return false, "high-hallucination-risk"
	}
	if adj.Confidence < minConfidence {
		return false, "below-confidence-threshold"
	}
	return true, ""
}

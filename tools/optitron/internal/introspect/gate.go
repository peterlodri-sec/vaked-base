package introspect
import (
	"github.com/peterlodri-sec/vaked-base/tools/optitron/internal/ledger"
)
func PassesGate(r Review, minConfidence float64) (bool, string) {
	if !r.Approved {
		return false, "not-approved"
	}
	if !r.Novel {
		return false, "not-novel"
	}
	if !r.Grounded {
		return false, "not-grounded-in-telemetry"
	}
	if !r.Actionable {
		return false, "not-actionable"
	}
	if r.Confidence < minConfidence {
		return false, "below-confidence-threshold"
	}
	return true, ""
}
func PriorTitles(path string) []string {
	entries, _ := ledger.Load(path)
	var out []string
	for _, e := range entries {
		ev, _ := e.Payload["event"].(string)
		if ev != "found" && ev != "rejected" {
			continue
		}
		if t, ok := e.Payload["title"].(string); ok && t != "" {
			out = append(out, t)
		}
	}
	return out
}
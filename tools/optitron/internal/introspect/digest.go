package introspect
import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"os/exec"
	"sort"
	"strings"
	"time"
	"github.com/peterlodri-sec/vaked-base/tools/optitron/internal/ledger"
)
type ModelStats struct {
	Calls            int
	Errors           int
	Truncated        int
	Cost             float64
	PromptTokens     int
	CompletionTokens int
	LatencyP50       float64
	LatencyP95       float64
}
type Economy struct {
	WindowDays float64 `json:"window_days"`
	WindowCost float64 `json:"window_cost"`
	PerDay     float64 `json:"per_day"`
	PerWeek    float64 `json:"per_week"`
	PerMonth   float64 `json:"per_month"`
}
func num(v any) float64 {
	switch x := v.(type) {
	case float64:
		return x
	case int:
		return float64(x)
	case json.Number:
		f, _ := x.Float64()
		return f
	case string:
		var f float64
		fmt.Sscanf(x, "%g", &f)
		return f
	}
	return 0
}
func obsTokens(o map[string]any) (int, int) {
	pin := num(o["promptTokens"])
	pout := num(o["completionTokens"])
	if pin == 0 || pout == 0 {
		if u, ok := o["usage"].(map[string]any); ok {
			if pin == 0 {
				pin = num(u["input"])
			}
			if pout == 0 {
				pout = num(u["output"])
			}
		}
	}
	return int(pin), int(pout)
}
func latencyPercentiles(vals []float64) (float64, float64) {
	if len(vals) == 0 {
		return 0, 0
	}
	s := append([]float64(nil), vals...)
	sort.Float64s(s)
	at := func(pct float64) float64 {
		k := int(pct/100*float64(len(s)-1) + 0.5)
		if k < 0 {
			k = 0
		}
		if k >= len(s) {
			k = len(s) - 1
		}
		return s[k]
	}
	return at(50), at(95)
}
type CostFn func(model string, prompt, completion int) float64
func AggregateByModel(observations []map[string]any, cost CostFn) map[string]*ModelStats {
	type acc struct {
		s   *ModelStats
		lat []float64
	}
	tmp := map[string]*acc{}
	for _, o := range observations {
		model, _ := o["model"].(string)
		if model == "" {
			model = "unknown"
		}
		a := tmp[model]
		if a == nil {
			a = &acc{s: &ModelStats{}}
			tmp[model] = a
		}
		a.s.Calls++
		statusMsg, _ := o["statusMessage"].(string)
		if strings.EqualFold(fmt.Sprint(o["level"]), "ERROR") || statusMsg != "" {
			a.s.Errors++
		}
		if strings.EqualFold(fmt.Sprint(o["finishReason"]), "length") {
			a.s.Truncated++
		}
		pin, pout := obsTokens(o)
		a.s.PromptTokens += pin
		a.s.CompletionTokens += pout
		srv := num(o["calculatedTotalCost"])
		if srv <= 0 {
			srv = num(o["totalCost"])
		}
		if srv > 0 {
			a.s.Cost += srv
		} else if cost != nil {
			a.s.Cost += cost(model, pin, pout)
		}
		if lat := num(o["latency"]); lat > 0 { // skip absent/zero — they'd skew p50/p95 low
			a.lat = append(a.lat, lat)
		}
	}
	out := map[string]*ModelStats{}
	for m, a := range tmp {
		p50, p95 := latencyPercentiles(a.lat)
		a.s.LatencyP50 = round(p50, 3)
		a.s.LatencyP95 = round(p95, 3)
		a.s.Cost = round(a.s.Cost, 4)
		out[m] = a.s
	}
	return out
}
func SpanCounts(observations []map[string]any) map[string]int {
	c := map[string]int{}
	for _, o := range observations {
		n, _ := o["name"].(string)
		if n == "" {
			n = "?"
		}
		c[n]++
	}
	return c
}
func Project(windowCost, windowDays float64) Economy {
	perDay := 0.0
	if windowDays > 0 {
		perDay = windowCost / windowDays
	}
	return Economy{
		WindowDays: windowDays, WindowCost: round(windowCost, 4),
		PerDay: round(perDay, 4), PerWeek: round(perDay*7, 2), PerMonth: round(perDay*30.4, 2),
	}
}
func IngestWindow(windowDays float64) (string, string) {
	now := time.Now().UTC()
	start := now.Add(-time.Duration(windowDays * 24 * float64(time.Hour)))
	const f = "2006-01-02T15:04:05Z"
	return start.Format(f), now.Format(f)
}
func BuildDigest(byModel map[string]*ModelStats, spans map[string]int, ledgerStats, ciStats map[string]any, windowDays float64) (string, Economy) {
	total := 0.0
	for _, s := range byModel {
		total += s.Cost
	}
	econ := Project(total, windowDays)
	var b strings.Builder
	fmt.Fprintf(&b, "# Fleet telemetry digest — last %gd\n\n", windowDays)
	if len(byModel) > 0 {
		b.WriteString("## Langfuse (per model)\n")
		b.WriteString("| model | calls | err | trunc | p50s | p95s | cost$ | tok(in/out) |\n")
		b.WriteString("|-------|------:|----:|------:|-----:|-----:|------:|-------------|\n")
		models := make([]string, 0, len(byModel))
		for m := range byModel {
			models = append(models, m)
		}
		sort.Slice(models, func(i, j int) bool { return byModel[models[i]].Calls > byModel[models[j]].Calls })
		for _, m := range models {
			s := byModel[m]
			fmt.Fprintf(&b, "| %s | %d | %d | %d | %g | %g | %.4f | %d/%d |\n",
				m, s.Calls, s.Errors, s.Truncated, s.LatencyP50, s.LatencyP95, s.Cost, s.PromptTokens, s.CompletionTokens)
		}
		if len(spans) > 0 {
			b.WriteString("\nspans: " + topSpans(spans, 12) + "\n")
		}
	} else {
		b.WriteString("## Langfuse: (no observations / keys absent)\n")
	}
	lj, _ := json.MarshalIndent(ledgerStats, "", "  ")
	b.WriteString("\n## Ledgers\n```json\n" + string(lj) + "\n```\n")
	if len(ciStats) > 0 {
		cj, _ := json.MarshalIndent(ciStats, "", "  ")
		b.WriteString("\n## CI (recent)\n```json\n" + string(cj) + "\n```\n")
	}
	fmt.Fprintf(&b, "\n## Economy (normal, non-optimistic — from measured window cost)\n"+
		"- window: $%.4f over %gd\n- **/day $%.4f · /week $%.2f · /month $%.2f**\n",
		econ.WindowCost, windowDays, econ.PerDay, econ.PerWeek, econ.PerMonth)
	return b.String(), econ
}
func topSpans(spans map[string]int, n int) string {
	type kv struct {
		k string
		v int
	}
	arr := make([]kv, 0, len(spans))
	for k, v := range spans {
		arr = append(arr, kv{k, v})
	}
	sort.Slice(arr, func(i, j int) bool { return arr[i].v > arr[j].v })
	if len(arr) > n {
		arr = arr[:n]
	}
	parts := make([]string, len(arr))
	for i, e := range arr {
		parts[i] = fmt.Sprintf("%s×%d", e.k, e.v)
	}
	return strings.Join(parts, ", ")
}
func LedgerStats(ralphPath, optitronPath string) map[string]any {
	out := map[string]any{}
	out["ralph"] = ledgerKinds(ralphPath)
	out["optitron"] = ledgerKinds(optitronPath)
	return out
}
func ledgerKinds(path string) map[string]any {
	entries, err := ledger.Load(path)
	if err != nil {
		return map[string]any{"error": err.Error()}
	}
	kinds := map[string]int{}
	for _, e := range entries {
		k, _ := e.Payload["event"].(string)
		if k == "" {
			k = "?"
		}
		kinds[k]++
	}
	return map[string]any{"events": len(entries), "by_kind": kinds}
}
func CIStats(ctx context.Context, repoRoot, repoGH string) map[string]any {
	cmd := exec.CommandContext(ctx, "gh", "run", "list", "--repo", repoGH, "--limit", "60",
		"--json", "name,conclusion")
	cmd.Dir = repoRoot
	out, err := cmd.Output()
	if err != nil {
		return nil
	}
	var runs []map[string]any
	if json.Unmarshal(out, &runs) != nil {
		return nil
	}
	failing := map[string]int{}
	for _, r := range runs {
		if fmt.Sprint(r["conclusion"]) == "failure" {
			failing[fmt.Sprint(r["name"])]++
		}
	}
	if len(failing) == 0 {
		return nil
	}
	return map[string]any{"failing_workflows": failing}
}
func round(f float64, places int) float64 {
	scale := math.Pow(10, float64(places))
	return math.Round(f*scale) / scale
}
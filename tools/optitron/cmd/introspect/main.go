// Command introspect is the fleet self-improvement agent — a second binary in the
// optitron Go module that REUSES optitron's core (internal/ledger, internal/llm).
// It mines the fleet's own Langfuse telemetry (+ the hash-chained ledgers; ralph's
// is read-only — a live agent we never modify) over the last ≤2 days, auto-detects
// the most salient finding, ideates ONE novel solution, REVIEWS it (fail-closed),
// and hands a survivor to swe_af via an `agent`-labelled issue. Advisory: any
// failure logs and exits 0.
//
//	introspect run [--once] [--dry-run] [--window-days N] [--focus "…"] [--budget-total N]
//	introspect events [--replay]
package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"strconv"

	"github.com/peterlodri-sec/vaked-base/tools/optitron/internal/introspect"
	"github.com/peterlodri-sec/vaked-base/tools/optitron/internal/ledger"
)

func main() { os.Exit(realMain()) }

func realMain() int {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: introspect <run|events> [flags]")
		return 2
	}
	switch os.Args[1] {
	case "run":
		return cmdRun(os.Args[2:])
	case "events":
		return cmdEvents(os.Args[2:])
	default:
		fmt.Fprintf(os.Stderr, "unknown command %q\n", os.Args[1])
		return 2
	}
}

func cmdRun(args []string) int {
	fs := flag.NewFlagSet("run", flag.ContinueOnError)
	_ = fs.Bool("once", false, "single cycle (default)")
	dryRun := fs.Bool("dry-run", false, "build the digest + prompts + cost/economy estimate; no model calls")
	windowDays := fs.Float64("window-days", 2.0, "telemetry lookback window in days")
	focus := fs.String("focus", "", "optional operator finding to prioritise (else auto-detect)")
	budgetStr := fs.String("budget-total", envOr("INTROSPECT_BUDGET", "3.0"), "USD hard cap per run")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	budget, err := strconv.ParseFloat(*budgetStr, 64)
	if err != nil {
		budget = 3.0
	}
	cfg := introspect.LoadConfig(*windowDays, budget, *focus)
	if err := introspect.Run(context.Background(), cfg, *dryRun); err != nil {
		fmt.Printf("::warning::introspect: %v\n", err)
	}
	return 0 // advisory — never hard-fail CI
}

func cmdEvents(args []string) int {
	fs := flag.NewFlagSet("events", flag.ContinueOnError)
	replay := fs.Bool("replay", false, "print each finding")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	cfg := introspect.LoadConfig(2.0, 3.0, "")
	entries, err := ledger.Load(cfg.EventsPath)
	if err != nil {
		fmt.Printf("::warning::introspect: %v\n", err)
		return 0
	}
	ok := ledger.VerifyChain(entries)
	found := 0
	for _, e := range entries {
		if ev, _ := e.Payload["event"].(string); ev == "found" {
			found++
			if *replay {
				fmt.Printf("  - %v (%v) %v\n", e.Payload["title"], e.Payload["bot"], e.Payload["issue"])
			}
		}
	}
	status := "OK"
	if !ok {
		status = "BROKEN"
	}
	fmt.Printf("introspect events: %d · chain %s · findings: %d\n", len(entries), status, found)
	if !ok {
		return 1
	}
	return 0
}

func envOr(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

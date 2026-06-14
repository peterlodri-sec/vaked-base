package run

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"sync"

	"github.com/peterlodri-sec/vaked-base/tools/optitron/internal/gate"
)

// --- Budget: a goroutine-safe spend guard shared across the worker pool. Every
// model call checks Over() first and records its cost, so total spend can't run
// away regardless of how many candidates are processed concurrently. ---

type Budget struct {
	mu    sync.Mutex
	spent float64
	cap   float64
}

func NewBudget(capUSD float64) *Budget { return &Budget{cap: capUSD} }

// Over reports whether the cap is reached (checked before each call).
func (b *Budget) Over() bool {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.spent >= b.cap
}

// Spend records cost and returns the running total.
func (b *Budget) Spend(cost float64) float64 {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.spent += cost
	return b.spent
}

// Spent returns the running total.
func (b *Budget) Spent() float64 {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.spent
}

// --- Novelty: deterministic "already applied in THIS repo?" via git grep, plus
// the ledger title dedupe handled by the caller. ---

// KnownInRepo is true iff the grep-able signature already appears in the repo.
func KnownInRepo(repoRoot, signature string) bool {
	sig := signature
	if len(sig) < 4 {
		return false
	}
	cmd := exec.Command("git", "-C", repoRoot, "grep", "-qiF", sig)
	return cmd.Run() == nil // exit 0 ⇒ found
}

// --- Benchmark: compile + run the model's micro-bench, parse the sentinel.
// Honest gate: no toolchain / no green run ⇒ (nil, …) and the finding abstains. ---

// RunBench compiles and runs a BenchSpec, returning the measured result. A nil
// result means "could not reproduce" — which the gate treats as a hard fail.
func RunBench(ctx context.Context, spec gate.BenchSpec, enabled bool) (*gate.BenchResult, error) {
	if !enabled {
		return nil, nil
	}
	d, err := os.MkdirTemp("", "optitron-bench-")
	if err != nil {
		return nil, err
	}
	defer os.RemoveAll(d)

	var src, exe string
	var compile *exec.Cmd
	switch spec.Lang {
	case "rust":
		src, exe = filepath.Join(d, "b.rs"), filepath.Join(d, "b")
		compile = exec.CommandContext(ctx, "rustc", "-O", "-o", exe, src)
	case "c":
		src, exe = filepath.Join(d, "b.c"), filepath.Join(d, "b")
		compile = exec.CommandContext(ctx, "cc", "-O2", "-o", exe, src)
	default:
		return nil, fmt.Errorf("unsupported bench lang %q", spec.Lang)
	}
	if err := os.WriteFile(src, []byte(spec.Source), 0o644); err != nil {
		return nil, err
	}
	if out, err := compile.CombinedOutput(); err != nil {
		return nil, fmt.Errorf("compile failed: %s", trim(string(out), 200))
	}
	runOut, err := exec.CommandContext(ctx, exe).Output()
	if err != nil {
		return nil, fmt.Errorf("bench run nonzero exit: %w", err)
	}
	res, ok := gate.ParseBenchOutput(string(runOut))
	if !ok {
		return nil, nil
	}
	return &res, nil
}

func trim(s string, n int) string {
	if len(s) > n {
		return s[:n]
	}
	return s
}

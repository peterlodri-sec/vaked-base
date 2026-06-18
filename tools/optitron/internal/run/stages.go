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
type Budget struct {
	mu    sync.Mutex
	spent float64
	cap   float64
}
func NewBudget(capUSD float64) *Budget { return &Budget{cap: capUSD} }
func (b *Budget) Over() bool {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.spent >= b.cap
}
func (b *Budget) Spend(cost float64) float64 {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.spent += cost
	return b.spent
}
func (b *Budget) Spent() float64 {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.spent
}
func KnownInRepo(repoRoot, signature string) bool {
	sig := signature
	if len(sig) < 4 {
		return false
	}
	cmd := exec.Command("git", "-C", repoRoot, "grep", "-qiF", sig)
	return cmd.Run() == nil // exit 0 ⇒ found
}
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
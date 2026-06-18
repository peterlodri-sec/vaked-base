package run
import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"github.com/peterlodri-sec/vaked-base/tools/optitron/internal/gate"
)
func IssueBody(c gate.Candidate, v gate.Verify, b *gate.BenchResult, adj gate.Adjudication) string {
	var srcs strings.Builder
	for _, s := range c.Sources {
		fmt.Fprintf(&srcs, "- [%s] %s: %s\n  > %s\n", s.Kind, s.Org, s.URL, s.Quote)
	}
	return fmt.Sprintf(
		"**Optimization (optitron finding):** %s\n\n"+
			"**Area:** `%s` · **Confidence:** %.2f · **Hallucination risk:** %s\n\n"+
			"## Mechanism\n%s\n\n"+
			"## Measured\nbaseline `%.0fns` → optimized `%.0fns` (**%.1f%%** faster, reproduced)\n\n"+
			"## Independent sources (%d)\n%s\n"+
			"## Cross-check\n%s\n\n"+
			"_Filed by vaked-optitron. Labelled `agent` to hand off to the swe_af workflow "+
			"(plan → code → review → publish). Re-verify the benchmark before implementing._\n",
		c.Title, c.Area, adj.Confidence, adj.HallucinationRisk, c.Mechanism,
		b.BaselineNs, b.OptimizedNs, b.Delta*100, v.IndependentCount, srcs.String(), v.Rationale)
}
func (c *Config) CreateAgentIssue(ctx context.Context, title, body string) (string, error) {
	if c.DryAct {
		return "dry-run://issue", nil
	}
	tmp, err := os.CreateTemp("", "optitron-issue-*.md")
	if err != nil {
		return "", err
	}
	defer os.Remove(tmp.Name())
	if _, err := tmp.WriteString(body); err != nil {
		return "", err
	}
	tmp.Close()
	args := []string{"issue", "create", "--title", title, "--body-file", tmp.Name(), "--label", "agent"}
	if repo := os.Getenv("GITHUB_REPOSITORY"); repo != "" {
		args = append(args, "--repo", repo)
	}
	out, err := exec.CommandContext(ctx, "gh", args...).Output()
	if err != nil {
		return "", fmt.Errorf("gh issue create: %w", err)
	}
	return strings.TrimSpace(string(out)), nil
}
func (c *Config) Announce(cand gate.Candidate, b *gate.BenchResult, issueURL string) error {
	if c.DryAct {
		return nil
	}
	pct := fmt.Sprintf("%.0f%%", b.Delta*100)
	toot := fmt.Sprintf("optitron found a %s optimization: %s. %s faster on a reproduced micro-bench, "+
		"2+ independent sources. Handed to swe_af. %s", cand.Area, cand.Title, pct, issueURL)
	if len(toot) > 480 {
		toot = toot[:480]
	}
	tg := fmt.Sprintf("🛰️ optitron finding (%s): %s\n%s faster (reproduced) · handed to swe_af\n%s",
		cand.Area, cand.Title, pct, issueURL)
	for path, text := range map[string]string{c.TootPath: toot, c.TelegramPath: tg} {
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			return err
		}
		if err := os.WriteFile(path, []byte(text+"\n"), 0o644); err != nil {
			return err
		}
	}
	return nil
}
package introspect

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/peterlodri-sec/vaked-base/tools/optitron/internal/ledger"
	"github.com/peterlodri-sec/vaked-base/tools/optitron/internal/llm"
)

const repoGH = "peterlodri-sec/vaked-base"

// Run executes one introspect cycle: ingest → detect → ideate → review → act.
// Advisory and fail-closed: any error logs and returns nil so CI never goes red,
// and nothing is posted unless the review gate passes.
func Run(ctx context.Context, cfg *Config, dryRun bool) error {
	purpose := readFileOr(cfg.PurposePath,
		"You are the fleet introspect agent. Surface ONE novel, grounded improvement from the "+
			"fleet's own telemetry, or nothing.")

	client := llm.New(cfg.APIKey, strings.TrimSuffix(cfg.BaseURL, "/chat/completions"), cfg.Prices)
	costFn := func(model string, pin, pout int) float64 { return client.CostOf(model, pin, pout) }

	// --- Ingest (read-only): Langfuse + the ledgers (ralph is live, read only) + CI ---
	lf := NewLangfuse(cfg.LangfuseHost, cfg.LangfusePublic, cfg.LangfuseSecret)
	from, to := IngestWindow(cfg.WindowDays)
	obs := lf.Query("/api/public/observations",
		map[string]string{"type": "GENERATION", "fromStartTime": from, "toStartTime": to}, 20)
	byModel := AggregateByModel(obs, costFn)
	spans := SpanCounts(obs)
	ledgerStats := LedgerStats(cfg.RalphEventsPath, cfg.OptitronEventsPath)
	ciStats := CIStats(ctx, cfg.RepoRoot, repoGH)
	digest, econ := BuildDigest(byModel, spans, ledgerStats, ciStats, cfg.WindowDays)

	if dryRun {
		return dryReport(cfg, client, digest, econ)
	}
	if cfg.APIKey == "" {
		fmt.Println("::notice::introspect: no API key (OPENROUTER_API_KEY/RALPH_API_KEY) — skipping")
		return nil
	}

	lw, err := ledger.Open(cfg.EventsPath)
	if err != nil {
		return fmt.Errorf("open introspect ledger: %w", err)
	}
	spent := 0.0

	// 1. detect the single most salient finding
	var finding Finding
	if c, e := client.CallJSON(ctx, cfg.DetectModel, DetectMessages(purpose, digest, cfg.Focus),
		DetectSchema, 1200, "", &finding); e != nil {
		spent += c
		appendEvent(lw, map[string]any{"event": "error", "stage": "detect", "msg": short(e)})
		fmt.Printf("::warning::introspect: detect failed: %v\n", e)
		return nil
	} else {
		spent += c
	}
	if finding.Finding == "" {
		appendEvent(lw, map[string]any{"event": "none", "reason": "no-finding", "cost": round(spent, 5), "economy": econ})
		fmt.Println("::notice::introspect: no finding surfaced — abstaining")
		summary(introSummary(econ, &finding, false, spent, "", ""))
		return nil
	}

	// 2. ideate ONE novel solution
	var idea Idea
	if c, e := client.CallJSON(ctx, cfg.IdeateModel, IdeateMessages(purpose, finding, digest),
		IdeateSchema, 2500, "medium", &idea); e != nil {
		spent += c
		appendEvent(lw, map[string]any{"event": "error", "stage": "ideate", "msg": short(e)})
		return nil
	} else {
		spent += c
	}
	title := strings.TrimSpace(idea.Title)
	if title == "" {
		appendEvent(lw, map[string]any{"event": "none", "reason": "no-idea", "cost": round(spent, 5)})
		return nil
	}

	// deterministic novelty before spending on review
	for _, t := range PriorTitles(cfg.EventsPath) {
		if t == title {
			appendEvent(lw, map[string]any{"event": "rejected", "title": title, "reason": "already-filed"})
			fmt.Printf("::notice::introspect: rejected '%s': already filed\n", title)
			return nil
		}
	}
	if idea.Signature != "" && knownInRepo(cfg.RepoRoot, idea.Signature) {
		appendEvent(lw, map[string]any{"event": "rejected", "title": title, "reason": "known-in-repo"})
		fmt.Printf("::notice::introspect: rejected '%s': signature already in repo\n", title)
		return nil
	}
	if spent >= cfg.Budget {
		appendEvent(lw, map[string]any{"event": "none", "reason": "budget", "cost": round(spent, 5)})
		return nil
	}

	// 3. always review (skeptical, fail-closed gate)
	var review Review
	if c, e := client.CallJSON(ctx, cfg.ReviewModel, ReviewMessages(purpose, finding, idea, digest),
		ReviewSchema, 1500, "medium", &review); e != nil {
		spent += c
		appendEvent(lw, map[string]any{"event": "error", "stage": "review", "msg": short(e)})
		return nil
	} else {
		spent += c
	}
	if passed, reason := PassesGate(review, cfg.MinConfidence); !passed {
		appendEvent(lw, map[string]any{"event": "rejected", "title": title, "reason": reason,
			"confidence": review.Confidence})
		fmt.Printf("::notice::introspect: rejected '%s': %s\n", title, reason)
		summary(introSummary(econ, &finding, false, spent, title, ""))
		return nil
	}

	// 4. act — hand off to swe_af + announce (gated behind the passing review)
	issueURL := "(dry-act)"
	if !cfg.DryAct {
		issueURL = createAgentIssue(ctx, cfg, finding, idea, review, econ)
		stageAnnounce(cfg, idea, econ, issueURL)
	}
	appendEvent(lw, map[string]any{"event": "found", "title": title, "bot": finding.Bot,
		"confidence": review.Confidence, "issue": issueURL, "cost": round(spent, 5), "economy": econ})
	fmt.Printf("::notice::introspect: FOUND '%s' → %s (conf %.2f)\n", title, issueURL, review.Confidence)
	summary(introSummary(econ, &finding, true, spent, title, issueURL))
	return nil
}

func dryReport(cfg *Config, client *llm.Client, digest string, econ Economy) error {
	est := client.CostOf(cfg.DetectModel, 12000, 3000) +
		client.CostOf(cfg.IdeateModel, 12000, 3000) +
		client.CostOf(cfg.ReviewModel, 12000, 3000)
	fmt.Println("=== fleet introspect dry-run ===")
	fmt.Printf("detect: %s\nideate: %s\nreview: %s\n", cfg.DetectModel, cfg.IdeateModel, cfg.ReviewModel)
	fmt.Printf("per-run est ~$%.3f; daily hard cap $%.2f\n", est, cfg.Budget)
	fmt.Printf("economy (measured $%.4f/%gd): /day $%.4f · /week $%.2f · /month $%.2f\n",
		econ.WindowCost, econ.WindowDays, econ.PerDay, econ.PerWeek, econ.PerMonth)
	fmt.Println("--- digest (system = PURPOSE.md) ---")
	if len(digest) > 1800 {
		digest = digest[:1800]
	}
	fmt.Println(digest)
	return nil
}

// --- act helpers ---

func createAgentIssue(ctx context.Context, cfg *Config, f Finding, idea Idea, r Review, econ Economy) string {
	body := issueBody(f, idea, r, econ)
	bf := filepath.Join(filepath.Dir(cfg.EventsPath), ".introspect-issue.md")
	if err := os.WriteFile(bf, []byte(body), 0o644); err != nil {
		return "(issue-write-failed)"
	}
	cmd := exec.CommandContext(ctx, "gh", "issue", "create", "--repo", repoGH,
		"--title", "[introspect] "+idea.Title, "--body-file", bf, "--label", "agent")
	cmd.Dir = cfg.RepoRoot
	out, err := cmd.Output()
	if err != nil {
		fmt.Printf("::warning::introspect: gh issue create: %v\n", err)
		return "(issue-create-failed)"
	}
	return strings.TrimSpace(string(out))
}

func issueBody(f Finding, idea Idea, r Review, econ Economy) string {
	var tf strings.Builder
	for _, t := range idea.TargetFiles {
		if t != "" {
			fmt.Fprintf(&tf, "- `%s`\n", t)
		}
	}
	if tf.Len() == 0 {
		tf.WriteString("- (none named)\n")
	}
	return fmt.Sprintf(
		"**Fleet self-improvement idea (introspect):** %s\n\n"+
			"**Finding** (`%s` · severity %s): %s\n\n> evidence: %s\n\n"+
			"## Mechanism\n%s\n\n## Why it's novel\n%s\n\n## Expected effect\n%s\n\n"+
			"## Grounding (telemetry)\n%s\n\n## Target files\n%s\n"+
			"## Review\napproved=%t · novel=%t · grounded=%t · confidence=%.2f\n\n> %s\n\n"+
			"## Fleet economy (normal, non-optimistic; last %gd)\n"+
			"measured $%.4f → **/day $%.4f · /week $%.2f · /month $%.2f**\n\n"+
			"_Filed by the introspect agent (reads ralph's live loop + Langfuse; never modifies them). "+
			"Labelled `agent` to hand off to swe_af. Re-verify before implementing._\n",
		idea.Title, f.Bot, f.Severity, f.Finding, f.Evidence,
		idea.Mechanism, idea.NoveltyRationale, idea.ExpectedEffect, idea.Evidence, tf.String(),
		r.Approved, r.Novel, r.Grounded, r.Confidence, r.Critique,
		econ.WindowDays, econ.WindowCost, econ.PerDay, econ.PerWeek, econ.PerMonth)
}

func stageAnnounce(cfg *Config, idea Idea, econ Economy, issueURL string) {
	toot := fmt.Sprintf("introspect filed a fleet improvement: %s. Grounded in 2 days of our own "+
		"Langfuse traces. Fleet spend ~$%.0f/mo. Handed to swe_af. %s", idea.Title, econ.PerMonth, issueURL)
	if len(toot) > 480 {
		toot = toot[:480]
	}
	tg := fmt.Sprintf("🔬 introspect: %s\ngrounded in fleet telemetry · ~$%.0f/mo spend · handed to swe_af\n%s",
		idea.Title, econ.PerMonth, issueURL)
	for path, text := range map[string]string{cfg.TootPath: toot, cfg.TelegramPath: tg} {
		_ = os.MkdirAll(filepath.Dir(path), 0o755)
		if err := os.WriteFile(path, []byte(text+"\n"), 0o644); err != nil {
			fmt.Printf("::warning::introspect: staging %s: %v\n", path, err)
		}
	}
}

func knownInRepo(repoRoot, signature string) bool {
	sig := strings.TrimSpace(signature)
	if len(sig) < 4 {
		return false
	}
	cmd := exec.Command("git", "-C", repoRoot, "grep", "-qiF", sig)
	return cmd.Run() == nil
}

func appendEvent(lw *ledger.Writer, payload map[string]any) {
	if _, err := lw.Append(payload); err != nil {
		fmt.Printf("::warning::introspect: ledger append: %v\n", err)
	}
}

func introSummary(econ Economy, f *Finding, found bool, spent float64, title, url string) string {
	head := "## fleet-introspect\n\nfound: **" + map[bool]string{true: "yes", false: "no (abstained)"}[found] + "**"
	if found && strings.HasPrefix(url, "http") {
		head += fmt.Sprintf(" — [%s](%s)", title, url)
	} else if found {
		head += " — " + title
	}
	fin := "\n\nfinding: (none)"
	if f != nil && f.Finding != "" {
		fin = "\n\nfinding: " + f.Finding
	}
	return fmt.Sprintf("%s%s\n\neconomy (normal, last %gd): /day $%.4f · /week $%.2f · /month $%.2f\n\nspend this run: $%.4f",
		head, fin, econ.WindowDays, econ.PerDay, econ.PerWeek, econ.PerMonth, spent)
}

func summary(md string) {
	path := os.Getenv("GITHUB_STEP_SUMMARY")
	if path == "" {
		return
	}
	if f, err := os.OpenFile(path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644); err == nil {
		defer f.Close()
		_, _ = f.WriteString(md + "\n")
	}
}

func short(e error) string {
	s := e.Error()
	if len(s) > 160 {
		return s[:160]
	}
	return s
}

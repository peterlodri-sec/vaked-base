package run

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"sync"
	"sync/atomic"

	"golang.org/x/sync/errgroup"

	"github.com/peterlodri-sec/vaked-base/tools/optitron/internal/gate"
	"github.com/peterlodri-sec/vaked-base/tools/optitron/internal/ledger"
	"github.com/peterlodri-sec/vaked-base/tools/optitron/internal/llm"
)

// crawlFanout controls how many source families crawl concurrently; candidateWorkers
// caps how many candidates are verified/benched/adjudicated in parallel.
const candidateWorkers = 4

// sourceFamilies are the in-scope crawl lanes fanned out across goroutines — each
// gets the shared hint plus a lane focus, broadening recall within one budget.
var sourceFamilies = []string{
	"arXiv compiler & PL papers (cs.PL/cs.DC) and recent LLVM/MLIR optimization-pass work",
	"LLVM / Cranelift / GCC release notes, RFCs, and codegen changelogs",
	"Zig compiler & std-lib changelog, devlog, and release notes",
	"Rust compiler/codegen: rustc-perf, MIR opt, LLVM bumps, and the Rust performance book",
	"Memory-allocator literature: mimalloc, snmalloc, tcmalloc, jemalloc papers & benchmarks",
}

// Logger is the CI-facing logger (::notice:: / ::warning:: in Actions).
type Logger struct {
	Notice  func(string)
	Warn    func(string)
	Summary func(string)
}

// Funnel is the per-run accounting printed to the CI step summary.
type Funnel struct {
	Crawled, Novel, Confirmed, Found int32
}

// Crawl runs one full crawl→novelty→verify→bench→adjudicate→act cycle. It is
// fail-closed and advisory: any stage short of the bar discards the candidate,
// and an empty result (abstain) is the designed, correct outcome.
func Crawl(ctx context.Context, cfg *Config, log *Logger, dryRun bool) error {
	skill := ReadFileOr(cfg.SkillPath, "You are vaked-optitron, a strict optimization crawler.")
	purpose := ReadFileOr(cfg.PurposePath, "Find ONE novel, proven optimization or nothing.")

	if dryRun {
		return dryRunReport(cfg, skill, purpose, log)
	}
	if cfg.APIKey == "" {
		log.Notice("no API key (OPENROUTER_API_KEY/RALPH_API_KEY) — skipping")
		return nil
	}

	lw, err := ledger.Open(cfg.EventsPath)
	if err != nil {
		return fmt.Errorf("open ledger: %w", err)
	}
	client := llm.New(cfg.APIKey, baseChatURL(cfg.BaseURL), cfg.Prices)
	client.Notice, client.Warn = log.Notice, log.Warn
	budget := NewBudget(cfg.BudgetTotal)
	var funnel Funnel

	// --- Stage 1: crawl fan-out (Generator). One concurrent call per source
	// family; merge + de-dupe candidates by title. ---
	candidates, crawlCost := crawlFanout(ctx, cfg, client, skill, purpose, lw.PriorTitles(), budget, log)
	budget.Spend(crawlCost)
	inScope := candidates[:0]
	seen := map[string]bool{}
	for _, c := range candidates {
		if gate.InScope(c.Area) && !seen[c.Title] {
			seen[c.Title] = true
			inScope = append(inScope, c)
		}
	}
	atomic.StoreInt32(&funnel.Crawled, int32(len(inScope)))
	mustAppend(lw, log, map[string]any{"event": "crawl", "candidates": len(inScope), "cost": round(budget.Spent())})
	log.Notice(fmt.Sprintf("crawled %d in-scope candidates ($%.4f)", len(inScope), budget.Spent()))

	// --- Stage 2: deterministic novelty (Parser, cheap, sequential). ---
	prior := strset(lw.PriorTitles())
	var survivors []gate.Candidate
	for _, c := range inScope {
		switch {
		case c.Signature != "" && KnownInRepo(cfg.RepoRoot, c.Signature):
			mustAppend(lw, log, rejected(c.Title, "known-in-repo"))
		case prior[c.Title]:
			mustAppend(lw, log, rejected(c.Title, "already-found"))
		case !gate.SourcesIndependent(c.Sources, cfg.MinSources):
			mustAppend(lw, log, rejected(c.Title, "sources-not-independent"))
		default:
			atomic.AddInt32(&funnel.Novel, 1)
			survivors = append(survivors, c)
		}
	}

	// --- Stage 3-6: bounded worker-pool. Each candidate runs verify→bench→
	// adjudicate→gate concurrently; the FIRST to clear the gate wins, acts, and
	// cancels the rest (one finding per run, parallelized). ---
	runCtx, cancel := context.WithCancel(ctx)
	defer cancel()
	var winOnce sync.Once
	g, gctx := errgroup.WithContext(runCtx)
	g.SetLimit(candidateWorkers)

	for _, c := range survivors {
		c := c
		g.Go(func() error {
			if gctx.Err() != nil || budget.Over() {
				return nil
			}
			processCandidate(gctx, cfg, client, lw, log, skill, c, budget, &funnel, &winOnce, cancel)
			return nil
		})
	}
	_ = g.Wait()

	if atomic.LoadInt32(&funnel.Found) == 0 {
		mustAppend(lw, log, map[string]any{"event": "none", "crawled": int(funnel.Crawled), "cost": round(budget.Spent())})
		log.Notice("no finding cleared the gate today (abstaining — that is success)")
	}
	log.Summary(fmt.Sprintf("## optitron crawl\n\nfunnel: %d crawled → %d novel → %d confirmed → **%d found**\n\nspend: $%.4f / $%.2f cap",
		funnel.Crawled, funnel.Novel, funnel.Confirmed, funnel.Found, budget.Spent(), cfg.BudgetTotal))
	return nil
}

// processCandidate is one worker: the skeptical Reasoner cross-check, the
// Generator's reproduced benchmark, the Reasoner's adjudication, then the Parser
// gate. On a pass it claims the single win via winOnce.
func processCandidate(ctx context.Context, cfg *Config, client *llm.Client, lw *ledger.Writer, log *Logger,
	skill string, c gate.Candidate, budget *Budget, funnel *Funnel, winOnce *sync.Once, cancel context.CancelFunc) {

	// 3. adversarial cross-check (Reasoner, with reasoning effort).
	var v gate.Verify
	cost, err := client.CallJSON(ctx, cfg.VerifyModel, llm.BuildVerifyMessages(skill, c), llm.VerifySchema, 2000, "medium", &v)
	budget.Spend(cost)
	if err != nil {
		if ctx.Err() == nil {
			mustAppend(lw, log, rejected(c.Title, trim("verify-error:"+err.Error(), 120)))
		}
		return
	}
	if !v.Independent || !v.ClaimSupported {
		mustAppend(lw, log, rejected(c.Title, "cross-check-failed"))
		return
	}
	atomic.AddInt32(&funnel.Confirmed, 1)

	// 4. benchmark (Generator emits, the harness compiles + runs).
	var bench *gate.BenchResult
	var spec gate.BenchSpec
	cost, err = client.CallJSON(ctx, cfg.BenchModel, llm.BuildBenchMessages(skill, c), llm.BenchSchema, 3000, "", &spec)
	budget.Spend(cost)
	if err == nil {
		if res, berr := RunBench(ctx, spec, cfg.RunBench); berr != nil {
			log.Warn("bench: " + berr.Error())
		} else {
			bench = res
		}
	}

	// 5. adjudicate (Reasoner certainty score).
	var adj gate.Adjudication
	cost, err = client.CallJSON(ctx, cfg.VerifyModel, llm.BuildAdjudicateMessages(skill, c, v, bench), llm.AdjudicateSchema, 1200, "medium", &adj)
	budget.Spend(cost)
	if err != nil {
		if ctx.Err() == nil {
			mustAppend(lw, log, rejected(c.Title, trim("adjudicate-error:"+err.Error(), 120)))
		}
		return
	}

	// 6. strict gate.
	passed, reason := gate.PassesGate(v, bench, adj, cfg.MinSources, cfg.MinConfidence, cfg.MinDelta)
	if !passed {
		rej := rejected(c.Title, reason)
		rej["confidence"] = adj.Confidence
		mustAppend(lw, log, rej)
		log.Notice(fmt.Sprintf("rejected '%s': %s", c.Title, reason))
		return
	}

	// Claim the single win. Only the first passer acts.
	acted := false
	winOnce.Do(func() {
		acted = true
		url, ierr := cfg.CreateAgentIssue(ctx, "[optitron] "+c.Title, IssueBody(c, v, bench, adj))
		if ierr != nil {
			log.Warn("issue create: " + ierr.Error())
			url = "(issue-create-failed)"
		}
		if aerr := cfg.Announce(c, bench, url); aerr != nil {
			log.Warn("announce: " + aerr.Error())
		}
		mustAppend(lw, log, map[string]any{"event": "found", "title": c.Title, "area": c.Area,
			"confidence": adj.Confidence, "delta": bench.Delta, "issue": url, "cost": round(budget.Spent())})
		atomic.StoreInt32(&funnel.Found, 1)
		log.Notice(fmt.Sprintf("FOUND '%s' → %s (%.1f%% faster, conf %.2f)", c.Title, url, bench.Delta*100, adj.Confidence))
		cancel() // one finding per run — stop the other workers
	})
	_ = acted
}

// crawlFanout issues one crawl call per source family concurrently and merges the
// candidates. Budget is checked per lane; the shared client tracks token spend.
func crawlFanout(ctx context.Context, cfg *Config, client *llm.Client, skill, purpose string,
	priorTitles []string, budget *Budget, log *Logger) ([]gate.Candidate, float64) {

	var (
		mu   sync.Mutex
		all  []gate.Candidate
		cost float64
	)
	g, gctx := errgroup.WithContext(ctx)
	g.SetLimit(len(sourceFamilies))
	for _, fam := range sourceFamilies {
		fam := fam
		g.Go(func() error {
			if budget.Over() {
				return nil
			}
			hint := cfg.SourcesHint + "\n\nFocus this lane on: " + fam
			var out struct {
				Candidates []gate.Candidate `json:"candidates"`
			}
			c, err := client.CallJSON(gctx, cfg.CrawlModel, llm.BuildCrawlMessages(skill, purpose, hint, priorTitles), llm.CrawlSchema, 4000, "", &out)
			mu.Lock()
			cost += c
			if err == nil {
				all = append(all, out.Candidates...)
			} else if gctx.Err() == nil {
				log.Warn("crawl lane failed: " + err.Error())
			}
			mu.Unlock()
			return nil
		})
	}
	_ = g.Wait()
	// stable order for determinism in logs/tests
	sort.SliceStable(all, func(i, j int) bool { return all[i].Title < all[j].Title })
	return all, cost
}

func dryRunReport(cfg *Config, skill, purpose string, log *Logger) error {
	client := llm.New(cfg.APIKey, cfg.BaseURL, cfg.Prices)
	est := 0.0
	for _, m := range []string{cfg.CrawlModel, cfg.VerifyModel, cfg.BenchModel} {
		est += client.CostOf(m, 30000, 15000)
	}
	fmt.Println("=== optitron dry-run (Go/Eino) ===")
	fmt.Printf("crawl  model: %s\nverify model: %s\nbench  model: %s\n", cfg.CrawlModel, cfg.VerifyModel, cfg.BenchModel)
	fmt.Printf("crawl fan-out lanes: %d · candidate workers: %d\n", len(sourceFamilies), candidateWorkers)
	fmt.Printf("gate: >=%d independent sources, bench delta >=%.0f%%, confidence >=%.2f\n",
		cfg.MinSources, cfg.MinDelta*100, cfg.MinConfidence)
	fmt.Printf("per-candidate est ~$%.3f; daily hard cap $%.2f\n", est, cfg.BudgetTotal)
	fmt.Println("--- crawl prompt (system = SKILL.md) ---")
	msgs := llm.BuildCrawlMessages(skill, purpose, cfg.SourcesHint, nil)
	body := msgs[len(msgs)-1].Content
	if len(body) > 1200 {
		body = body[:1200]
	}
	fmt.Println(body)
	return nil
}

// --- helpers ---

func rejected(title, reason string) map[string]any {
	return map[string]any{"event": "rejected", "title": title, "reason": reason}
}

func mustAppend(lw *ledger.Writer, log *Logger, payload map[string]any) {
	if _, err := lw.Append(payload); err != nil {
		log.Warn("ledger append: " + err.Error())
	}
}

func strset(ss []string) map[string]bool {
	m := make(map[string]bool, len(ss))
	for _, s := range ss {
		m[s] = true
	}
	return m
}

func round(f float64) float64 { return float64(int64(f*1e5)) / 1e5 }

// baseChatURL normalises a configured base URL to the chat-completions endpoint
// Eino's component expects (it appends /chat/completions to the v1 root itself).
func baseChatURL(u string) string {
	return strings.TrimSuffix(u, "/chat/completions")
}

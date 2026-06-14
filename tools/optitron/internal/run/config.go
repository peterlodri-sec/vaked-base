// Package run is optitron's orchestration layer: configuration, the goroutine
// pipeline (crawl fan-out + bounded candidate worker-pool), the budget guard,
// and the deterministic novelty / benchmark / act stages.
//
// PentestGPT lineage: the pipeline runs three cooperating "modules" over a shared
// candidate set — a Generator (crawl + bench codegen), a Reasoner (verify +
// adjudicate), and a Parser (the gate package). Cross-run memory is the
// hash-chained ledger; bounded iteration = "one finding per run" + the budget cap.
package run

import (
	"encoding/json"
	"os"
	"path/filepath"

	"github.com/peterlodri-sec/vaked-base/tools/optitron/internal/llm"
)

// Config is the fully-resolved runtime configuration for one crawl.
type Config struct {
	RepoRoot string
	// Paths (resolved under RepoRoot).
	EventsPath   string
	SkillPath    string
	PurposePath  string
	SourcesPath  string
	TootPath     string
	TelegramPath string

	APIKey  string
	BaseURL string

	CrawlModel  string
	VerifyModel string
	BenchModel  string

	// Gate thresholds (from sources.json, overridable).
	MinSources    int
	MinConfidence float64
	MinDelta      float64
	SourcesHint   string

	BudgetTotal float64
	RunBench    bool
	DryAct      bool

	Prices map[string]llm.Price
}

const openrouterURL = "https://openrouter.ai/api/v1/chat/completions"

// Refreshed model roster (June 2026): a web-enabled crawler for breadth, the
// current frontier reasoner on the anti-hallucination gate, a top coder for the
// reproduction benchmark. All env-overridable; the budget cap is the real guard.
const (
	defaultCrawlModel  = "openai/gpt-5.5:online"
	defaultVerifyModel = "anthropic/claude-opus-4.8"
	defaultBenchModel  = "deepseek/deepseek-v4-flash"
)

// defaultPrices is per-1M-token (prompt, completion) — rough, for the budget
// estimate only. Includes the new defaults and the legacy slugs for override compat.
func defaultPrices() map[string]llm.Price {
	return map[string]llm.Price{
		"openai/gpt-5.5":                     {In: 1.25, Out: 10.0},
		"openai/gpt-5.5:online":              {In: 1.25, Out: 10.0},
		"anthropic/claude-opus-4.8":          {In: 5.0, Out: 25.0},
		"anthropic/claude-fable-5":           {In: 10.0, Out: 50.0},
		"deepseek/deepseek-v4-flash":         {In: 0.2, Out: 0.4},
		"deepseek/deepseek-v3.2":             {In: 0.28, Out: 0.42},
		"openai/gpt-oss-120b":                {In: 0.1, Out: 0.5},
		"openai/gpt-oss-120b:online":         {In: 0.1, Out: 0.5},
		"qwen/qwen3-235b-a22b-thinking-2507": {In: 0.15, Out: 0.85},
	}
}

func env(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

// LoadConfig resolves paths, env, and sources.json into a Config.
func LoadConfig(budgetTotal float64) (*Config, error) {
	root := findRepoRoot()
	c := &Config{
		RepoRoot:      root,
		EventsPath:    filepath.Join(root, "tools", "optitron", "state", "events.jsonl"),
		SkillPath:     filepath.Join(root, ".claude", "skills", "vaked-optitron", "SKILL.md"),
		PurposePath:   filepath.Join(root, "tools", "optitron", "PURPOSE.md"),
		SourcesPath:   filepath.Join(root, "tools", "optitron", "sources.json"),
		TootPath:      filepath.Join(root, ".github", "social", "toot.txt"),
		TelegramPath:  filepath.Join(root, ".github", "social", "telegram.txt"),
		APIKey:        env("OPENROUTER_API_KEY", os.Getenv("RALPH_API_KEY")),
		BaseURL:       env("OPTITRON_BASE_URL", openrouterURL),
		CrawlModel:    env("OPTITRON_CRAWL_MODEL", defaultCrawlModel),
		VerifyModel:   env("OPTITRON_VERIFY_MODEL", defaultVerifyModel),
		BenchModel:    env("OPTITRON_BENCH_MODEL", defaultBenchModel),
		MinSources:    2,
		MinConfidence: 0.80,
		MinDelta:      0.10,
		BudgetTotal:   budgetTotal,
		RunBench:      env("OPTITRON_RUN_BENCH", "1") == "1",
		DryAct:        os.Getenv("OPTITRON_DRY_ACT") != "",
		Prices:        defaultPrices(),
	}

	// sources.json — hint + thresholds.
	var sc struct {
		Hint          string  `json:"hint"`
		MinSources    int     `json:"min_sources"`
		MinConfidence float64 `json:"min_confidence"`
		MinBenchDelta float64 `json:"min_bench_delta"`
	}
	if b, err := os.ReadFile(c.SourcesPath); err == nil {
		_ = json.Unmarshal(b, &sc)
		if sc.Hint != "" {
			c.SourcesHint = sc.Hint
		}
		if sc.MinSources > 0 {
			c.MinSources = sc.MinSources
		}
		if sc.MinConfidence > 0 {
			c.MinConfidence = sc.MinConfidence
		}
		if sc.MinBenchDelta > 0 {
			c.MinDelta = sc.MinBenchDelta
		}
	}
	if c.SourcesHint == "" {
		c.SourcesHint = "arXiv; LLVM/Cranelift/Zig/Rust release notes & RFCs; mimalloc/snmalloc/tcmalloc papers; godbolt/bench write-ups."
	}
	return c, nil
}

// ReadFileOr returns the file content, or def on any error.
func ReadFileOr(path, def string) string {
	if b, err := os.ReadFile(path); err == nil {
		return string(b)
	}
	return def
}

// findRepoRoot walks up from cwd looking for a .git dir; OPTITRON_REPO overrides.
func findRepoRoot() string {
	if r := os.Getenv("OPTITRON_REPO"); r != "" {
		return r
	}
	dir, err := os.Getwd()
	if err != nil {
		return "."
	}
	for {
		if fi, err := os.Stat(filepath.Join(dir, ".git")); err == nil && (fi.IsDir() || !fi.IsDir()) {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			return mustWd()
		}
		dir = parent
	}
}

func mustWd() string {
	d, _ := os.Getwd()
	if d == "" {
		return "."
	}
	return d
}

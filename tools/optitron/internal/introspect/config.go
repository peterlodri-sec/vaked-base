// Package introspect is the fleet self-improvement agent — a second binary in the
// optitron Go module that REUSES optitron's core (internal/ledger, internal/llm)
// rather than re-implementing it. It mines the fleet's OWN telemetry — the live
// Langfuse traces plus the hash-chained ledgers (ralph's is read-only: it is a
// live agent we never modify) — over the last ≤2 days, auto-detects the most
// salient finding, ideates ONE novel solution, REVIEWS it behind a fail-closed
// gate, and hands a survivor to swe_af via an `agent`-labelled issue.
package introspect

import (
	"os"
	"path/filepath"

	"github.com/peterlodri-sec/vaked-base/tools/optitron/internal/llm"
)

// Config is the fully-resolved runtime configuration for one introspect run.
type Config struct {
	RepoRoot string

	EventsPath         string // introspect's OWN hash-chained ledger
	RalphEventsPath    string // ralph's live ledger — READ ONLY
	OptitronEventsPath string // optitron's crawl ledger — READ ONLY
	PurposePath        string
	TootPath           string
	TelegramPath       string

	APIKey  string
	BaseURL string

	DetectModel string
	IdeateModel string
	ReviewModel string

	WindowDays    float64
	Budget        float64
	Focus         string
	MinConfidence float64
	DryAct        bool

	LangfuseHost   string
	LangfusePublic string
	LangfuseSecret string

	Prices map[string]llm.Price
}

const openrouterV1 = "https://openrouter.ai/api/v1/chat/completions"

// June-2026 defaults: cheap triage to detect, the frontier reasoner to ideate +
// review (the anti-hallucination crux). All env-overridable; the budget is the guard.
const (
	defaultDetectModel = "deepseek/deepseek-v4-flash"
	defaultIdeateModel = "anthropic/claude-opus-4.8"
	defaultReviewModel = "anthropic/claude-opus-4.8"
)

func defaultPrices() map[string]llm.Price {
	return map[string]llm.Price{
		"deepseek/deepseek-v4-flash": {In: 0.2, Out: 0.4},
		"deepseek/deepseek-v3.2":     {In: 0.28, Out: 0.42},
		"anthropic/claude-opus-4.8":  {In: 5.0, Out: 25.0},
		"anthropic/claude-fable-5":   {In: 10.0, Out: 50.0},
		"openai/gpt-5.5":             {In: 1.25, Out: 10.0},
		"openai/gpt-oss-120b":        {In: 0.1, Out: 0.5},
	}
}

func env(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

// LoadConfig resolves paths, env, and models into a Config.
func LoadConfig(windowDays, budget float64, focus string) *Config {
	root := findRepoRoot()
	return &Config{
		RepoRoot:           root,
		EventsPath:         filepath.Join(root, "tools", "optitron", "state", "introspect.jsonl"),
		RalphEventsPath:    filepath.Join(root, "tools", "ralph", "state", "events.jsonl"),
		OptitronEventsPath: filepath.Join(root, "tools", "optitron", "state", "events.jsonl"),
		PurposePath:        filepath.Join(root, "tools", "optitron", "internal", "introspect", "PURPOSE.md"),
		TootPath:           filepath.Join(root, ".github", "social", "toot.txt"),
		TelegramPath:       filepath.Join(root, ".github", "social", "telegram.txt"),
		APIKey:             env("OPENROUTER_API_KEY", os.Getenv("RALPH_API_KEY")),
		BaseURL:            env("INTROSPECT_BASE_URL", openrouterV1),
		DetectModel:        env("INTROSPECT_DETECT_MODEL", defaultDetectModel),
		IdeateModel:        env("INTROSPECT_IDEATE_MODEL", defaultIdeateModel),
		ReviewModel:        env("INTROSPECT_REVIEW_MODEL", defaultReviewModel),
		WindowDays:         windowDays,
		Budget:             budget,
		Focus:              focus,
		MinConfidence:      0.75,
		DryAct:             os.Getenv("INTROSPECT_DRY_ACT") != "",
		LangfuseHost:       env("LANGFUSE_HOST", os.Getenv("LANGFUSE_BASE_URL")),
		LangfusePublic:     os.Getenv("LANGFUSE_PUBLIC_KEY"),
		LangfuseSecret:     os.Getenv("LANGFUSE_SECRET_KEY"),
		Prices:             defaultPrices(),
	}
}

func readFileOr(path, def string) string {
	if b, err := os.ReadFile(path); err == nil {
		return string(b)
	}
	return def
}

func findRepoRoot() string {
	if r := os.Getenv("OPTITRON_REPO"); r != "" {
		return r
	}
	dir, err := os.Getwd()
	if err != nil {
		return "."
	}
	for {
		if _, err := os.Stat(filepath.Join(dir, ".git")); err == nil {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			if wd, _ := os.Getwd(); wd != "" {
				return wd
			}
			return "."
		}
		dir = parent
	}
}

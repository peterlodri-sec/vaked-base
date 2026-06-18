package main
import (
	"context"
	"flag"
	"fmt"
	"os"
	"strconv"
	"github.com/peterlodri-sec/vaked-base/tools/optitron/internal/run"
)
func notice(s string) { fmt.Printf("::notice::optitron: %s\n", s) }
func warn(s string)   { fmt.Printf("::warning::optitron: %s\n", s) }
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
func main() {
	os.Exit(realMain())
}
func realMain() int {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: optitron <crawl|events> [flags]")
		return 2
	}
	switch os.Args[1] {
	case "crawl":
		return cmdCrawl(os.Args[2:])
	case "events":
		return cmdEvents(os.Args[2:])
	default:
		fmt.Fprintf(os.Stderr, "unknown command %q\n", os.Args[1])
		return 2
	}
}
func cmdCrawl(args []string) int {
	fs := flag.NewFlagSet("crawl", flag.ContinueOnError)
	_ = fs.Bool("once", false, "single cycle (default; reserved for parity)")
	dryRun := fs.Bool("dry-run", false, "build prompts + cost estimate only, no network")
	budgetStr := fs.String("budget-total", envOr("OPTITRON_BUDGET", "4.0"), "USD hard cap per run")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	budget, err := strconv.ParseFloat(*budgetStr, 64)
	if err != nil {
		warn("bad --budget-total: " + err.Error())
		budget = 4.0
	}
	cfg, err := run.LoadConfig(budget)
	if err != nil {
		warn("config: " + err.Error())
		return 0 // advisory
	}
	log := &run.Logger{Notice: notice, Warn: warn, Summary: summary}
	if err := run.Crawl(context.Background(), cfg, log, *dryRun); err != nil {
		warn("crawl: " + err.Error())
	}
	return 0 // advisory — never hard-fail CI
}
func cmdEvents(args []string) int {
	fs := flag.NewFlagSet("events", flag.ContinueOnError)
	replay := fs.Bool("replay", false, "print each finding")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	cfg, err := run.LoadConfig(4.0)
	if err != nil {
		warn("config: " + err.Error())
		return 0
	}
	if err := run.Events(cfg, *replay); err != nil {
		return 1 // chain broken
	}
	return 0
}
func envOr(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}
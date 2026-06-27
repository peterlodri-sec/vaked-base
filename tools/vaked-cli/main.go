// vaked-cli — compiled CLI for Vaked development workflows.
//
// Subcommands:
//
//	mlir check              Validate .td files (needs mlir-tblgen)
//	mlir env                Show MLIR toolchain status
//	mlir validate <file>    Run Stage-0 pass pipeline
//	seal sign <path> <mem>  Produce a votive seal
//	seal admit <file>       Validate a seal (ADMIT/REFUSE)
//	seal verify <file>      Validate with verbose output
//	proxy discover          Scan local network for LLM endpoints
//	proxy status            Show running proxy services
//	proxy data              Show proxy disk usage
//	proxy apply <file>      Deploy a proxy config
//	task list               List all Taskfile tasks
//	task run <name> [args]  Run a Taskfile task
//	deploy dev              Deploy vaked.dev via wrangler
//	deploy lang             Deploy vaked-lang.org via wrangler
//	deploy docs             Autogen + deploy docs to vaked-lang.org
//	cf zones                List Cloudflare zones
//	cf dns <zone>           List DNS records for a zone
//	cf status               Quick health check
//
// Build:
//
//	go build -o vaked-cli .                    # native
//	GOOS=linux GOARCH=amd64 CGO_ENABLED=0 \
//	  go build -o vaked-cli-linux-x86_64 .     # cross-compile for dev-cx53
package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

// repoRoot resolves relative to the binary location.
var repoRoot string

func resolveRepoRoot(exe string) string {
	if v := os.Getenv("VAKED_REPO_ROOT"); v != "" {
		if fi, err := os.Stat(v); err == nil && fi.IsDir() {
			return v
		}
	}
	real, _ := filepath.EvalSymlinks(exe)
	dir := filepath.Dir(real)
	for {
		if _, err := os.Stat(filepath.Join(dir, "flake.nix")); err == nil {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			break
		}
		dir = parent
	}
	if up := filepath.Dir(filepath.Dir(filepath.Dir(real))); up != "." && up != "/" {
		return up
	}
	return ""
}

func init() {
	exe, _ := os.Executable()
	repoRoot = resolveRepoRoot(exe)
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintf(os.Stderr, "Usage: vaked-cli <mlir|seal|proxy|task|deploy|docs|cf> <subcommand> [args]\n")
		os.Exit(1)
	}

	switch os.Args[1] {
	case "mlir":
		mlirCmd(os.Args[2:])
	case "seal":
		sealCmd(os.Args[2:])
	case "proxy":
		proxyCmd(os.Args[2:])
	case "task":
		taskCmd(os.Args[2:])
	case "deploy":
		deployCmd(os.Args[2:])
	case "docs":
		docsCmd(os.Args[2:])
	case "cf":
		cfCmd(os.Args[2:])
	default:
		fmt.Fprintf(os.Stderr, "unknown command: %s\n", os.Args[1])
		os.Exit(1)
	}
}

// ========================================================================== //
// MLIR subcommands
// ========================================================================== //

func mlirCmd(args []string) {
	if len(args) < 1 {
		fmt.Fprintln(os.Stderr, "Usage: vaked-cli mlir <check|env|validate> [args]")
		os.Exit(1)
	}
	switch args[0] {
	case "check":
		mlirCheck()
	case "env":
		mlirEnv()
	case "validate":
		if len(args) < 2 {
			fmt.Fprintln(os.Stderr, "Usage: vaked-cli mlir validate <file>")
			os.Exit(1)
		}
		mlirValidate(args[1])
	default:
		fmt.Fprintf(os.Stderr, "unknown mlir subcommand: %s\n", args[0])
		os.Exit(1)
	}
}

func mlirCheck() {
	if repoRoot == "" {
		fmt.Fprintln(os.Stderr, "vaked-cli: set VAKED_REPO_ROOT to the vaked-base source tree")
		os.Exit(1)
	}
	tg := findTblgen()
	if tg == "" {
		fmt.Fprintln(os.Stderr, "mlir-tblgen not found — install or 'nix develop .'")
		os.Exit(1)
	}
	tdFiles := []struct {
		name string
		path string
	}{
		{"vaked dialect", filepath.Join(repoRoot, "vakedc/mlir", "VakedDialect.td")},
		{"hcp dialect", filepath.Join(repoRoot, "vakedc/mlir", "HcpDialect.td")},
	}
	allOK := true
	for _, td := range tdFiles {
		r := runCmd(tg, "--gen-op-defs", td.path)
		if r.errCode == 0 {
			lines := len(strings.Split(string(r.out), "\n"))
			fmt.Printf("  PASS  %s: %d lines generated\n", td.name, lines)
		} else {
			fmt.Fprintf(os.Stderr, "  FAIL  %s: %s\n", td.name, strings.TrimSpace(string(r.err)))
			allOK = false
		}
	}
	if !allOK {
		os.Exit(1)
	}
}

func mlirEnv() {
	if repoRoot == "" {
		fmt.Fprintln(os.Stderr, "vaked-cli: set VAKED_REPO_ROOT to the vaked-base source tree")
		os.Exit(1)
	}
	tg := findTblgen()
	if tg != "" {
		fmt.Printf("mlir-tblgen: %s\n", tg)
		out, err := exec.Command(tg, "--version").Output()
		if err == nil {
			fmt.Printf("version:     %s", out)
		}
	} else {
		fmt.Println("mlir-tblgen: not found")
	}
	for _, name := range []string{"VakedDialect.td", "HcpDialect.td"} {
		path := filepath.Join(repoRoot, "vakedc/mlir", name)
		if fi, err := os.Stat(path); err == nil {
			fmt.Printf("  %s: OK (%d bytes)\n", name, fi.Size())
		} else {
			fmt.Printf("  %s: not found\n", name)
		}
	}
}

func mlirValidate(file string) {
	if repoRoot == "" {
		fmt.Fprintln(os.Stderr, "vaked-cli: set VAKED_REPO_ROOT to the vaked-base source tree")
		os.Exit(1)
	}
	fullPath := file
	if !filepath.IsAbs(file) {
		cwd, _ := os.Getwd()
		fullPath = filepath.Join(cwd, file)
	}
	cmd := exec.Command("python3", "-m", "vakedc", "passes", "--json", fullPath)
	cmd.Dir = repoRoot
	out, err := cmd.Output()
	if err != nil {
		fmt.Fprintf(os.Stderr, "passes failed: %v\n", err)
		os.Exit(1)
	}
	var result struct {
		Workflows   []interface{} `json:"workflows"`
		Diagnostics []struct {
			Code    string `json:"code"`
			Message string `json:"message"`
		} `json:"diagnostics"`
		Artifacts []string `json:"artifacts"`
		Status    string   `json:"status"`
	}
	if err := json.Unmarshal(out, &result); err != nil {
		fmt.Fprintf(os.Stderr, "parse error: %v\n", err)
		os.Exit(1)
	}
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	enc.Encode(result)
	if result.Status == "FAIL" {
		os.Exit(1)
	}
}

// ========================================================================== //
// Seal subcommands
// ========================================================================== //

func sealCmd(args []string) {
	if len(args) < 1 {
		fmt.Fprintln(os.Stderr, "Usage: vaked-cli seal <sign|admit|verify> [args]")
		os.Exit(1)
	}
	switch args[0] {
	case "sign":
		if len(args) < 3 {
			fmt.Fprintln(os.Stderr, "Usage: vaked-cli seal sign <path|hash> <membrane> [epoch]")
			os.Exit(1)
		}
		epoch := 1
		if len(args) >= 4 {
			epoch, _ = strconv.Atoi(args[3])
		}
		sealSign(args[1], args[2], epoch)
	case "admit":
		if len(args) < 2 {
			fmt.Fprintln(os.Stderr, "Usage: vaked-cli seal admit <provenance.json>")
			os.Exit(1)
		}
		sealAdmit(args[1], false)
	case "verify":
		if len(args) < 2 {
			fmt.Fprintln(os.Stderr, "Usage: vaked-cli seal verify <provenance.json>")
			os.Exit(1)
		}
		sealAdmit(args[1], true)
	default:
		fmt.Fprintf(os.Stderr, "unknown seal subcommand: %s\n", args[0])
		os.Exit(1)
	}
}

type VotiveSeal struct {
	Vaked         SealMeta `json:"vaked"`
	Membrane      string   `json:"membrane"`
	ClosureHash   string   `json:"closure_hash"`
	TopologyEpoch int      `json:"topology_epoch"`
	GeneratedAt   string   `json:"generated_at"`
	Signature     SealSig  `json:"signature"`
}

type SealMeta struct {
	Schema  string `json:"schema"`
	Version string `json:"version"`
}

type SealSig struct {
	Algorithm   string `json:"algorithm"`
	Value       string `json:"value"`
	PublicKey   string `json:"public_key,omitempty"`
	Placeholder bool   `json:"placeholder,omitempty"`
}

func sealSign(pathOrHash, membrane string, epoch int) {
	var closureHash string
	if len(pathOrHash) == 64 {
		if _, err := hex.DecodeString(pathOrHash); err == nil {
			closureHash = strings.ToLower(pathOrHash)
		}
	}
	if closureHash == "" {
		h := sha256.New()
		if err := walkHash(pathOrHash, h); err != nil {
			fmt.Fprintf(os.Stderr, "REFUSE: cannot hash %q: %v\n", pathOrHash, err)
			os.Exit(1)
		}
		closureHash = hex.EncodeToString(h.Sum(nil))
	}
	payload := map[string]interface{}{
		"vaked":          SealMeta{Schema: "votive-seal", Version: "1"},
		"membrane":       membrane,
		"closure_hash":   closureHash,
		"topology_epoch": epoch,
		"generated_at":   time.Now().UTC().Format("2006-01-02T15:04:05Z"),
	}
	canon, _ := json.Marshal(payload)
	mac := hmac.New(sha256.New, make([]byte, 32))
	mac.Write(canon)
	sig := mac.Sum(nil)
	seal := VotiveSeal{
		Vaked:         SealMeta{Schema: "votive-seal", Version: "1"},
		Membrane:      membrane,
		ClosureHash:   closureHash,
		TopologyEpoch: epoch,
		GeneratedAt:   time.Now().UTC().Format("2006-01-02T15:04:05Z"),
		Signature: SealSig{
			Algorithm:   "hmac-sha256-placeholder",
			Value:       base64.StdEncoding.EncodeToString(sig),
			Placeholder: true,
		},
	}
	fmt.Fprintln(os.Stderr, "vaked-cli: WARNING: HMAC-SHA256 placeholder — NOT post-quantum secure")
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	enc.Encode(seal)
}

func sealAdmit(path string, verbose bool) {
	data, err := os.ReadFile(path)
	if err != nil {
		fmt.Fprintln(os.Stderr, "REFUSE: cannot read seal —", err)
		os.Exit(1)
	}
	var seal VotiveSeal
	if err := json.Unmarshal(data, &seal); err != nil {
		fmt.Fprintln(os.Stderr, "REFUSE: invalid JSON —", err)
		os.Exit(1)
	}
	if seal.Membrane == "" || seal.ClosureHash == "" || seal.Signature.Algorithm == "" {
		fmt.Fprintln(os.Stderr, "REFUSE: missing required fields")
		os.Exit(1)
	}
	if seal.Signature.Algorithm == "hmac-sha256-placeholder" && seal.Signature.Placeholder {
		if verbose {
			fmt.Printf("ADMIT (placeholder): %s closure=%s epoch=%d\n",
				seal.Membrane, seal.ClosureHash, seal.TopologyEpoch)
			fmt.Fprintln(os.Stderr, "WARNING: HMAC key not available for re-verification")
		} else {
			fmt.Println("ADMIT")
		}
		return
	}
	fmt.Fprintln(os.Stderr, "REFUSE: unsupported algorithm", seal.Signature.Algorithm)
	os.Exit(1)
}

// ========================================================================== //
// Proxy subcommands
// ========================================================================== //

func proxyCmd(args []string) {
	if len(args) < 1 {
		fmt.Fprintln(os.Stderr, "Usage: vaked-cli proxy <discover|status|data|apply> [args]")
		os.Exit(1)
	}
	switch args[0] {
	case "discover":
		proxyDiscover()
	case "status":
		proxyStatus()
	case "data":
		proxyData()
	case "apply":
		if len(args) < 2 {
			fmt.Fprintln(os.Stderr, "Usage: vaked-cli proxy apply <config.yaml> [host]")
			os.Exit(1)
		}
		host := "localhost"
		if len(args) >= 3 {
			host = args[2]
		}
		proxyApply(args[1], host)
	default:
		fmt.Fprintf(os.Stderr, "unknown proxy subcommand: %s\n", args[0])
		os.Exit(1)
	}
}

func proxyDiscover() {
	results := []string{}
	c := exec.Command("ollama", "list")
	if out, err := c.Output(); err == nil {
		results = append(results, fmt.Sprintf("Ollama (localhost:11434):\n  %s", indentBlock(string(out), "  ")))
	} else {
		results = append(results, "Ollama: not running on localhost:11434")
	}
	for _, ep := range []string{
		"http://localhost:4000/health",
		"http://localhost:11434/api/tags",
		"http://localhost:8080/health",
	} {
		r := httpGet(ep)
		if r != "" {
			results = append(results, fmt.Sprintf("  ✓ %s", ep))
		} else {
			results = append(results, fmt.Sprintf("  ✗ %s", ep))
		}
	}
	for _, ep := range []string{
		"http://dev-cx53:4000/health",
		"http://dev-cx53:11434/api/tags",
	} {
		r := httpGet(ep)
		if r != "" {
			results = append(results, fmt.Sprintf("  ✓ remote %s", ep))
		} else {
			results = append(results, fmt.Sprintf("  ✗ remote %s (offline or no tailscale)", ep))
		}
	}
	fmt.Println("=== LLM endpoint discovery ===")
	for _, r := range results {
		fmt.Println(r)
	}
}

func proxyData() {
	home, _ := os.UserHomeDir()
	fmt.Println("=== LLM proxy data ===")
	paths := map[string]string{
		"Proxy DB + cache": home + "/.vaked/llmproxy",
		"Ollama blobs":     home + "/.ollama/models",
		"Ollama config":    home + "/.ollama",
		"Redis data":       "/tmp/vaked-redis",
	}
	for label, p := range paths {
		fi, err := os.Stat(p)
		if err != nil {
			fmt.Printf("  %s: %s\n", label, color("✗", "31"))
			continue
		}
		if !fi.IsDir() {
			fmt.Printf("  %s: %s (%d bytes)\n", label, color("✓", "32"), fi.Size())
			continue
		}
		files := 0
		var totalSize int64
		filepath.Walk(p, func(_ string, info os.FileInfo, err error) error {
			if err == nil {
				files++
				totalSize += info.Size()
			}
			return nil
		})
		mb := float64(totalSize) / 1024 / 1024
		fmt.Printf("  %s: %s (%d files, %.1f MB)\n", label, color("✓", "32"), files, mb)
	}
	c := exec.Command("ssh", "dev@dev-cx53",
		"du -sh ~/.vaked/llmproxy 2>/dev/null; echo '---'; du -sh ~/.ollama/models 2>/dev/null; echo '---'; du -sh ~/.cache/litellm 2>/dev/null || true",
	)
	if out, err := c.Output(); err == nil {
		fmt.Printf("\n  Remote dev-cx53:\n%s", indentBlock(string(out), "    "))
	}
}

func proxyStatus() {
	ports := []string{"11434", "4000", "8080", "3000"}
	fmt.Println("=== LLM proxy services ===")
	for _, port := range ports {
		ep := fmt.Sprintf("http://localhost:%s/health", port)
		r := httpGet(ep)
		if r != "" {
			fmt.Printf("  port %s: RUNNING\n", port)
		} else {
			fmt.Printf("  port %s: CLOSED\n", port)
		}
	}
}

func proxyApply(configPath, host string) {
	data, err := os.ReadFile(configPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "cannot read config: %v\n", err)
		os.Exit(1)
	}
	if host == "localhost" || host == "local" {
		dest := "deploy/llmproxy/proxy-mesh.yaml"
		if err := os.WriteFile(dest, data, 0644); err != nil {
			fmt.Fprintf(os.Stderr, "write config: %v\n", err)
			os.Exit(1)
		}
		fmt.Printf("Config written to %s\n", dest)
		fmt.Println("To start: litellm --config deploy/llmproxy/proxy-mesh.yaml --port 4000")
	} else {
		runCmd := fmt.Sprintf("ssh %s 'mkdir -p deploy/llmproxy && cat > deploy/llmproxy/proxy-mesh.yaml'", host)
		c := exec.Command("bash", "-c", runCmd)
		c.Stdin = strings.NewReader(string(data))
		if out, err := c.CombinedOutput(); err != nil {
			fmt.Fprintf(os.Stderr, "scp config to %s: %v\n  %s", host, err, string(out))
			os.Exit(1)
		}
		fmt.Printf("Config deployed to %s:deploy/llmproxy/proxy-mesh.yaml\n", host)
		fmt.Printf("To start on remote: ssh %s 'litellm --config deploy/llmproxy/proxy-mesh.yaml --port 4000'\n", host)
	}
}

// ========================================================================== //
// NEW: Task subcommands — list/run Taskfile tasks
// ========================================================================== //

func taskCmd(args []string) {
	if len(args) < 1 {
		fmt.Fprintln(os.Stderr, "Usage: vaked-cli task <list|run> [args]")
		os.Exit(1)
	}
	switch args[0] {
	case "list":
		taskList()
	case "run":
		if len(args) < 2 {
			fmt.Fprintln(os.Stderr, "Usage: vaked-cli task run <name> [-- args...]")
			os.Exit(1)
		}
		taskRun(args[1], args[2:])
	default:
		fmt.Fprintf(os.Stderr, "unknown task subcommand: %s\n", args[0])
		os.Exit(1)
	}
}

func taskList() {
	if repoRoot == "" {
		fmt.Fprintln(os.Stderr, "vaked-cli: set VAKED_REPO_ROOT")
		os.Exit(1)
	}
	cmd := exec.Command("task", "--list")
	cmd.Dir = repoRoot
	out, err := cmd.Output()
	if err != nil {
		fmt.Fprintf(os.Stderr, "task not found: install from https://taskfile.dev\n")
		os.Exit(1)
	}
	fmt.Println(string(out))
}

func taskRun(name string, args []string) {
	if repoRoot == "" {
		fmt.Fprintln(os.Stderr, "vaked-cli: set VAKED_REPO_ROOT")
		os.Exit(1)
	}
	argv := []string{name}
	argv = append(argv, args...)
	cmd := exec.Command("task", argv...)
	cmd.Dir = repoRoot
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.Stdin = os.Stdin
	if err := cmd.Run(); err != nil {
		os.Exit(1)
	}
}

// ========================================================================== //
// NEW: Deploy subcommands — wrangler pages deploy
// ========================================================================== //

func deployCmd(args []string) {
	if len(args) < 1 {
		fmt.Fprintln(os.Stderr, "Usage: vaked-cli deploy <dev|lang|docs|all>")
		os.Exit(1)
	}
	switch args[0] {
	case "dev":
		deployDev()
	case "lang":
		deployLang()
	case "docs":
		deployDocs()
	case "all":
		deployDev()
		deployLang()
	default:
		fmt.Fprintf(os.Stderr, "unknown deploy target: %s\n", args[0])
		os.Exit(1)
	}
}

func deployDev() {
	if repoRoot == "" {
		fmt.Fprintln(os.Stderr, "vaked-cli: set VAKED_REPO_ROOT")
		os.Exit(1)
	}
	fmt.Println("Deploying vaked.dev…")
	cmd := exec.Command("npx", "-y", "wrangler@3", "pages", "deploy",
		filepath.Join(repoRoot, "deploy/vaked.dev"),
		"--project-name=vaked-dev", "--branch=main")
	cmd.Dir = repoRoot
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		fmt.Fprintf(os.Stderr, "deploy vaked.dev failed: %v\n", err)
		os.Exit(1)
	}
}

func deployLang() {
	if repoRoot == "" {
		fmt.Fprintln(os.Stderr, "vaked-cli: set VAKED_REPO_ROOT")
		os.Exit(1)
	}
	fmt.Println("Deploying vaked-lang.org…")
	cmd := exec.Command("npx", "-y", "wrangler@3", "pages", "deploy",
		filepath.Join(repoRoot, "site"),
		"--project-name=vaked-lang", "--branch=main")
	cmd.Dir = repoRoot
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		fmt.Fprintf(os.Stderr, "deploy vaked-lang failed: %v\n", err)
		os.Exit(1)
	}
}

// ========================================================================== //
// NEW: Docs subcommands — autogen + deploy
// ========================================================================== //

func docsCmd(args []string) {
	if len(args) < 1 {
		fmt.Fprintln(os.Stderr, "Usage: vaked-cli docs <gen|deploy|all>")
		os.Exit(1)
	}
	switch args[0] {
	case "gen":
		docsGen()
	case "deploy":
		deployDocs()
	case "all":
		docsGen()
		deployDocs()
	default:
		fmt.Fprintf(os.Stderr, "unknown docs subcommand: %s\n", args[0])
		os.Exit(1)
	}
}

func docsGen() {
	if repoRoot == "" {
		fmt.Fprintln(os.Stderr, "vaked-cli: set VAKED_REPO_ROOT")
		os.Exit(1)
	}
	fmt.Println("Autogenerating docs from markdown…")
	cmd := exec.Command("python3",
		filepath.Join(repoRoot, "tools/docs-autogen.py"),
		"--source", filepath.Join(repoRoot, "docs"),
		"--output", filepath.Join(repoRoot, "site/docs"))
	cmd.Dir = repoRoot
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		fmt.Fprintf(os.Stderr, "docs gen failed: %v\n", err)
		os.Exit(1)
	}
	fmt.Println("Docs generated.")
}

func deployDocs() {
	if repoRoot == "" {
		fmt.Fprintln(os.Stderr, "vaked-cli: set VAKED_REPO_ROOT")
		os.Exit(1)
	}
	// Gen first, then deploy
	docsGen()
	deployLang()
}

// ========================================================================== //
// NEW: CF subcommands — Cloudflare API shortcuts
// ========================================================================== //

func cfCmd(args []string) {
	if len(args) < 1 {
		fmt.Fprintln(os.Stderr, "Usage: vaked-cli cf <zones|dns|status> [zone]")
		os.Exit(1)
	}
	switch args[0] {
	case "zones":
		cfZones()
	case "dns":
		if len(args) < 2 {
			fmt.Fprintln(os.Stderr, "Usage: vaked-cli cf dns <zone-name>")
			os.Exit(1)
		}
		cfDNS(args[1])
	case "status":
		cfStatus()  // account-scoped token: no /user/tokens/verify
	default:
		fmt.Fprintf(os.Stderr, "unknown cf subcommand: %s\n", args[0])
		os.Exit(1)
	}
}

func cfToken() string {
	home, _ := os.UserHomeDir()
	path := filepath.Join(home, ".cftok")
	data, err := os.ReadFile(path)
	if err != nil {
		fmt.Fprintf(os.Stderr, "cannot read ~/.cftok: %v\n", err)
		os.Exit(1)
	}
	// Parse API_TOKEN="..."
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, "API_TOKEN=") {
			val := strings.TrimPrefix(line, "API_TOKEN=")
			val = strings.Trim(val, `"'`)
			return val
		}
	}
	fmt.Fprintln(os.Stderr, "API_TOKEN not found in ~/.cftok")
	os.Exit(1)
	return ""
}

func cfAccountID() string {
	home, _ := os.UserHomeDir()
	path := filepath.Join(home, ".cftok")
	data, err := os.ReadFile(path)
	if err != nil {
		fmt.Fprintf(os.Stderr, "cannot read ~/.cftok: %v\n", err)
		os.Exit(1)
	}
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, "ACCOUNT_ID=") {
			val := strings.TrimPrefix(line, "ACCOUNT_ID=")
			val = strings.Trim(val, `"'`)
			return val
		}
	}
	fmt.Fprintln(os.Stderr, "ACCOUNT_ID not found in ~/.cftok")
	os.Exit(1)
	return ""
}

func cfZones() {
	token := cfToken()
	cmd := exec.Command("curl", "-sf",
		"-H", "Authorization: Bearer "+token,
		"https://api.cloudflare.com/client/v4/zones?per_page=50")
	out, err := cmd.Output()
	if err != nil {
		fmt.Fprintf(os.Stderr, "API call failed: %v\n", err)
		os.Exit(1)
	}
	var resp struct {
		Result []struct {
			Name   string `json:"name"`
			Plan   struct{ Name string } `json:"plan"`
			Status string `json:"status"`
		} `json:"result"`
	}
	if err := json.Unmarshal(out, &resp); err != nil {
		fmt.Fprintf(os.Stderr, "parse error: %v\n", err)
		os.Exit(1)
	}
	fmt.Println("Cloudflare Zones:")
	for _, z := range resp.Result {
		fmt.Printf("  %-25s %-15s %s\n", z.Name, z.Plan.Name, z.Status)
	}
}

func cfDNS(zoneName string) {
	token := cfToken()
	acct := cfAccountID()
	// Find zone ID by name
	cmd := exec.Command("curl", "-sf",
		"-H", "Authorization: Bearer "+token,
		fmt.Sprintf("https://api.cloudflare.com/client/v4/zones?name=%s", zoneName))
	out, _ := cmd.Output()
	var zoneResp struct {
		Result []struct{ Id string } `json:"result"`
	}
	json.Unmarshal(out, &zoneResp)
	if len(zoneResp.Result) == 0 {
		fmt.Fprintf(os.Stderr, "zone %q not found\n", zoneName)
		os.Exit(1)
	}
	zoneId := zoneResp.Result[0].Id
	_ = acct // available for future use

	// Fetch DNS records
	cmd2 := exec.Command("curl", "-sf",
		"-H", "Authorization: Bearer "+token,
		fmt.Sprintf("https://api.cloudflare.com/client/v4/zones/%s/dns_records?per_page=100", zoneId))
	out2, err := cmd2.Output()
	if err != nil {
		fmt.Fprintf(os.Stderr, "DNS fetch failed: %v\n", err)
		os.Exit(1)
	}
	var dnsResp struct {
		Result []struct {
			Name    string `json:"name"`
			Type    string `json:"type"`
			Content string `json:"content"`
			Proxied bool   `json:"proxied"`
		} `json:"result"`
	}
	if err := json.Unmarshal(out2, &dnsResp); err != nil {
		fmt.Fprintf(os.Stderr, "parse error: %v\n", err)
		os.Exit(1)
	}
	fmt.Printf("DNS records for %s:\n", zoneName)
	for _, r := range dnsResp.Result {
		prox := " P" 
		if !r.Proxied { prox = "  " }
		fmt.Printf("  %s%s %-40s → %s\n", r.Type, prox, r.Name, r.Content)
	}
}

func cfStatus() {
	token := cfToken()
	acct := cfAccountID()
	fmt.Println("=== Cloudflare Quick Health ===")
	// Count zones
	out, _ := exec.Command("curl", "-sf",
		"-H", "Authorization: Bearer "+token,
		"https://api.cloudflare.com/client/v4/zones?per_page=50").Output()
	var zr struct {
		Result []struct{ Name string } `json:"result"`
	}
	if err := json.Unmarshal(out, &zr); err == nil {
		fmt.Printf("  Zones:            %d\n", len(zr.Result))
		for _, z := range zr.Result {
			fmt.Printf("                     %s\n", z.Name)
		}
	}
	// Count Pages projects
	out, _ = exec.Command("curl", "-sf",
		"-H", "Authorization: Bearer "+token,
		fmt.Sprintf("https://api.cloudflare.com/client/v4/accounts/%s/pages/projects?per_page=50", acct)).Output()
	var pr struct {
		Result []struct{ Name string } `json:"result"`
	}
	if err := json.Unmarshal(out, &pr); err == nil {
		fmt.Printf("  Pages projects:   %d\n", len(pr.Result))
	}
}

// ========================================================================== //
// Helpers
// ========================================================================== //

func httpGet(url string) string {
	cmd := exec.Command("curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--connect-timeout", "3", url)
	out, err := cmd.Output()
	if err != nil {
		return ""
	}
	code := strings.TrimSpace(string(out))
	if code == "200" {
		return "200 OK"
	}
	return fmt.Sprintf("HTTP %s", code)
}

func color(s, code string) string {
	return "\033[" + code + "m" + s + "\033[0m"
}

func indentBlock(s, prefix string) string {
	lines := strings.Split(strings.TrimRight(s, "\n"), "\n")
	for i, line := range lines {
		lines[i] = prefix + line
	}
	return strings.Join(lines, "\n")
}

func findTblgen() string {
	for _, name := range []string{"mlir-tblgen"} {
		if p, err := exec.LookPath(name); err == nil {
			return p
		}
	}
	return ""
}

type cmdResult struct {
	out     []byte
	err     []byte
	errCode int
}

func runCmd(name string, args ...string) cmdResult {
	cmd := exec.Command(name, args...)
	cmd.Dir = repoRoot
	cmd.Env = os.Environ()
	var stdout, stderr strings.Builder
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	err := cmd.Run()
	result := cmdResult{out: []byte(stdout.String()), err: []byte(stderr.String())}
	if err != nil {
		result.errCode = 1
	}
	return result
}

func walkHash(path string, h io.Writer) error {
	info, err := os.Stat(path)
	if err != nil {
		return err
	}
	if !info.IsDir() {
		data, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		h.Write(data)
		return nil
	}
	return filepath.Walk(path, func(p string, fi os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if fi.IsDir() {
			return nil
		}
		data, err := os.ReadFile(p)
		if err != nil {
			return err
		}
		h.Write(data)
		return nil
	})
}

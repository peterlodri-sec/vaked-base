// vaked-cli — compiled CLI for Vaked development workflows.
//
// Subcommands:
//
//	mlir <check|env|validate>         MLIR toolchain
//	seal <sign|admit|verify>          Votive seals (RFC 0007)
//	proxy <discover|status|data|apply> LLM proxy mesh
//	task <list|run [-- args...]>      Taskfile tasks
//	deploy <dev|lang|docs|all>        Wrangler deploy
//	docs <gen|deploy|all>             Autogen + deploy docs
//	cf <zones|dns <zone>|status>      Cloudflare API shortcuts
//
// Build:
//
//	go build -o vaked-cli .                              # native
//	GOOS=linux GOARCH=amd64 CGO_ENABLED=0 \
//	  go build -o vaked-cli-linux-x86_64 .                # cross-compile
package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

// ── Globals (set once in init) ──

var repoRoot string

type cfCreds struct {
	token     string
	accountID string
}

var cf cfCreds

// ── Init ──

func init() {
	exe, _ := os.Executable()
	repoRoot = resolveRepoRoot(exe)
	cf = readCFCreds()
}

func resolveRepoRoot(exe string) string {
	if v := os.Getenv("VAKED_REPO_ROOT"); v != "" {
		if fi, err := os.Stat(v); err == nil && fi.IsDir() {
			return v
		}
	}
	// Walk up looking for flake.nix marker
	dir := filepath.Dir(exe)
	for {
		if _, err := os.Stat(filepath.Join(dir, "flake.nix")); err == nil {
			return dir
		}
		p := filepath.Dir(dir)
		if p == dir {
			break
		}
		dir = p
	}
	return ""
}

func readCFCreds() cfCreds {
	home, _ := os.UserHomeDir()
	data, err := os.ReadFile(filepath.Join(home, ".cftok"))
	if err != nil {
		return cfCreds{} // silent — commands check fields
	}
	c := cfCreds{}
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, "API_TOKEN=") {
			c.token = strings.Trim(strings.TrimPrefix(line, "API_TOKEN="), `"'`)
		}
		if strings.HasPrefix(line, "ACCOUNT_ID=") {
			c.accountID = strings.Trim(strings.TrimPrefix(line, "ACCOUNT_ID="), `"'`)
		}
	}
	return c
}

// ── Helpers ──

func requireRepo() {
	if repoRoot == "" {
		fmt.Fprintln(os.Stderr, "vaked-cli: cannot find repo root. Set VAKED_REPO_ROOT or run from vaked-base.")
		os.Exit(1)
	}
}

func requireCF() {
	if cf.token == "" {
		fmt.Fprintln(os.Stderr, "vaked-cli: cannot read Cloudflare credentials from ~/.cftok")
		os.Exit(1)
	}
}

func cfAPI(path string) ([]byte, error) {
	url := "https://api.cloudflare.com/client/v4" + path
	req, _ := http.NewRequest("GET", url, nil)
	req.Header.Set("Authorization", "Bearer "+cf.token)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	return io.ReadAll(resp.Body)
}

func wranglerDeploy(dir string, project string) {
	requireRepo()
	fmt.Printf("Deploying %s…\n", project)
	cmd := exec.Command("npx", "-y", "wrangler@3", "pages", "deploy",
		filepath.Join(repoRoot, dir),
		"--project-name="+project, "--branch=main")
	cmd.Dir = repoRoot
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		fmt.Fprintf(os.Stderr, "deploy %s failed: %v\n", project, err)
		os.Exit(1)
	}
}

func execInRepo(name string, args ...string) *exec.Cmd {
	requireRepo()
	cmd := exec.Command(name, args...)
	cmd.Dir = repoRoot
	return cmd
}

func jsonOut(v interface{}) {
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	enc.Encode(v)
}

func bail(format string, args ...interface{}) {
	fmt.Fprintf(os.Stderr, format+"\n", args...)
	os.Exit(1)
}

// ── main ──

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
		bail("unknown command: %s", os.Args[1])
	}
}

// ── MLIR ──

func mlirCmd(args []string) {
	if len(args) < 1 {
		bail("Usage: vaked-cli mlir <check|env|validate> [args]")
	}
	switch args[0] {
	case "check":
		mlirCheck()
	case "env":
		mlirEnv()
	case "validate":
		if len(args) < 2 {
			bail("Usage: vaked-cli mlir validate <file>")
		}
		mlirValidate(args[1])
	default:
		bail("unknown mlir subcommand: %s", args[0])
	}
}

func findTblgen() string {
	p, _ := exec.LookPath("mlir-tblgen")
	return p
}

func mlirCheck() {
	requireRepo()
	tg := findTblgen()
	if tg == "" {
		bail("mlir-tblgen not found — install or 'nix develop .'")
	}
	type tdFile struct{ name, path string }
	files := []tdFile{
		{"vaked dialect", filepath.Join(repoRoot, "vakedc/mlir", "VakedDialect.td")},
		{"hcp dialect", filepath.Join(repoRoot, "vakedc/mlir", "HcpDialect.td")},
	}
	ok := true
	for _, f := range files {
		cmd := exec.Command(tg, "--gen-op-defs", f.path)
		cmd.Dir = repoRoot
		out, err := cmd.Output()
		if err == nil {
			fmt.Printf("  PASS  %s: %d lines generated\n", f.name, len(strings.Split(string(out), "\n")))
		} else {
			fmt.Fprintf(os.Stderr, "  FAIL  %s: %v\n", f.name, err)
			ok = false
		}
	}
	if !ok {
		os.Exit(1)
	}
}

func mlirEnv() {
	requireRepo()
	if tg := findTblgen(); tg != "" {
		fmt.Printf("mlir-tblgen: %s\n", tg)
		if out, err := exec.Command(tg, "--version").Output(); err == nil {
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
	requireRepo()
	if !filepath.IsAbs(file) {
		cwd, _ := os.Getwd()
		file = filepath.Join(cwd, file)
	}
	out, err := execInRepo("python3", "-m", "vakedc", "passes", "--json", file).Output()
	if err != nil {
		bail("passes failed: %v", err)
	}
	var result struct {
		Diagnostics []struct {
			Code    string `json:"code"`
			Message string `json:"message"`
		} `json:"diagnostics"`
		Status string `json:"status"`
	}
	if err := json.Unmarshal(out, &result); err != nil {
		bail("parse error: %v", err)
	}
	jsonOut(result)
	if result.Status == "FAIL" {
		os.Exit(1)
	}
}

// ── Seal (RFC 0007) ──

type (
	VotiveSeal struct {
		Vaked         SealMeta `json:"vaked"`
		Membrane      string   `json:"membrane"`
		ClosureHash   string   `json:"closure_hash"`
		TopologyEpoch int      `json:"topology_epoch"`
		GeneratedAt   string   `json:"generated_at"`
		Signature     SealSig  `json:"signature"`
	}
	SealMeta struct {
		Schema  string `json:"schema"`
		Version string `json:"version"`
	}
	SealSig struct {
		Algorithm   string `json:"algorithm"`
		Value       string `json:"value"`
		PublicKey   string `json:"public_key,omitempty"`
		Placeholder bool   `json:"placeholder,omitempty"`
	}
)

func sealCmd(args []string) {
	if len(args) < 1 {
		bail("Usage: vaked-cli seal <sign|admit|verify> [args]")
	}
	switch args[0] {
	case "sign":
		if len(args) < 3 {
			bail("Usage: vaked-cli seal sign <path|hash> <membrane> [epoch]")
		}
		epoch := 1
		if len(args) >= 4 {
			epoch, _ = strconv.Atoi(args[3])
		}
		sealSign(args[1], args[2], epoch)
	case "admit":
		if len(args) < 2 {
			bail("Usage: vaked-cli seal admit <provenance.json>")
		}
		sealAdmit(args[1], false)
	case "verify":
		if len(args) < 2 {
			bail("Usage: vaked-cli seal verify <provenance.json>")
		}
		sealAdmit(args[1], true)
	default:
		bail("unknown seal subcommand: %s", args[0])
	}
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
			bail("REFUSE: cannot hash %q: %v", pathOrHash, err)
		}
		closureHash = hex.EncodeToString(h.Sum(nil))
	}
	seal := VotiveSeal{
		Vaked:         SealMeta{Schema: "votive-seal", Version: "1"},
		Membrane:      membrane,
		ClosureHash:   closureHash,
		TopologyEpoch: epoch,
		GeneratedAt:   time.Now().UTC().Format("2006-01-02T15:04:05Z"),
		Signature: SealSig{
			Algorithm:   "hmac-sha256-placeholder",
			Value:       base64.StdEncoding.EncodeToString(hmac.New(sha256.New, make([]byte, 32)).Sum(nil)),
			Placeholder: true,
		},
	}
	fmt.Fprintln(os.Stderr, "vaked-cli: WARNING: HMAC-SHA256 placeholder — NOT post-quantum secure")
	jsonOut(seal)
}

func sealAdmit(path string, verbose bool) {
	data, err := os.ReadFile(path)
	if err != nil {
		bail("REFUSE: cannot read seal — %v", err)
	}
	var seal VotiveSeal
	if err := json.Unmarshal(data, &seal); err != nil {
		bail("REFUSE: invalid JSON — %v", err)
	}
	if seal.Membrane == "" || seal.ClosureHash == "" || seal.Signature.Algorithm == "" {
		bail("REFUSE: missing required fields")
	}
	if seal.Signature.Algorithm == "hmac-sha256-placeholder" && seal.Signature.Placeholder {
		if verbose {
			fmt.Printf("ADMIT (placeholder): %s closure=%s epoch=%d\n", seal.Membrane, seal.ClosureHash, seal.TopologyEpoch)
			fmt.Fprintln(os.Stderr, "WARNING: HMAC key not available for re-verification")
		} else {
			fmt.Println("ADMIT")
		}
		return
	}
	bail("REFUSE: unsupported algorithm %s", seal.Signature.Algorithm)
}

// ── Proxy ──

func proxyCmd(args []string) {
	if len(args) < 1 {
		bail("Usage: vaked-cli proxy <discover|status|data|apply> [args]")
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
			bail("Usage: vaked-cli proxy apply <config.yaml> [host]")
		}
		host := "localhost"
		if len(args) >= 3 {
			host = args[2]
		}
		proxyApply(args[1], host)
	default:
		bail("unknown proxy subcommand: %s", args[0])
	}
}

func httpOK(url string) bool {
	req, _ := http.NewRequest("GET", url, nil)
	resp, err := http.DefaultClient.Do(req)
	return err == nil && resp.StatusCode == 200
}

func proxyDiscover() {
	fmt.Println("=== LLM endpoint discovery ===")
	// Ollama
	if out, err := exec.Command("ollama", "list").Output(); err == nil {
		fmt.Printf("Ollama (localhost:11434):\n  %s", indent(string(out), "  "))
	} else {
		fmt.Println("Ollama: not running on localhost:11434")
	}
	// Local endpoints
	for _, ep := range []string{
		"http://localhost:4000/health",
		"http://localhost:11434/api/tags",
		"http://localhost:8080/health",
	} {
		if httpOK(ep) {
			fmt.Printf("  ✓ %s\n", ep)
		} else {
			fmt.Printf("  ✗ %s\n", ep)
		}
	}
	// Remote (tailscale)
	for _, ep := range []string{
		"http://dev-cx53:4000/health",
		"http://dev-cx53:11434/api/tags",
	} {
		if httpOK(ep) {
			fmt.Printf("  ✓ remote %s\n", ep)
		} else {
			fmt.Printf("  ✗ remote %s (offline or no tailscale)\n", ep)
		}
	}
}

func proxyData() {
	home, _ := os.UserHomeDir()
	fmt.Println("=== LLM proxy data ===")
	dirs := map[string]string{
		"Proxy DB + cache": home + "/.vaked/llmproxy",
		"Ollama blobs":     home + "/.ollama/models",
		"Ollama config":    home + "/.ollama",
		"Redis data":       "/tmp/vaked-redis",
	}
	for label, p := range dirs {
		fi, err := os.Stat(p)
		if err != nil {
			fmt.Printf("  %s: ✗\n", label)
			continue
		}
		if !fi.IsDir() {
			fmt.Printf("  %s: ✓ (%d bytes)\n", label, fi.Size())
			continue
		}
		files := 0
		var total int64
		filepath.Walk(p, func(_ string, info os.FileInfo, err error) error {
			if err == nil {
				files++
				total += info.Size()
			}
			return nil
		})
		fmt.Printf("  %s: ✓ (%d files, %.1f MB)\n", label, files, float64(total)/1024/1024)
	}
	if out, err := exec.Command("ssh", "dev@dev-cx53",
		"du -sh ~/.vaked/llmproxy 2>/dev/null; echo '---'; du -sh ~/.ollama/models 2>/dev/null",
	).Output(); err == nil {
		fmt.Printf("\n  Remote dev-cx53:\n%s", indent(string(out), "    "))
	}
}

func proxyStatus() {
	fmt.Println("=== LLM proxy services ===")
	for _, port := range []string{"11434", "4000", "8080", "3000"} {
		ep := fmt.Sprintf("http://localhost:%s/health", port)
		if httpOK(ep) {
			fmt.Printf("  port %s: RUNNING\n", port)
		} else {
			fmt.Printf("  port %s: CLOSED\n", port)
		}
	}
}

func proxyApply(configPath, host string) {
	data, err := os.ReadFile(configPath)
	if err != nil {
		bail("cannot read config: %v", err)
	}
	dest := "deploy/llmproxy/proxy-mesh.yaml"
	if host == "localhost" || host == "local" {
		if err := os.WriteFile(dest, data, 0644); err != nil {
			bail("write config: %v", err)
		}
		fmt.Printf("Config written to %s\n", dest)
		fmt.Println("To start: litellm --config deploy/llmproxy/proxy-mesh.yaml --port 4000")
	} else {
		cmd := exec.Command("ssh", host, "mkdir -p deploy/llmproxy && cat > deploy/llmproxy/proxy-mesh.yaml")
		cmd.Stdin = strings.NewReader(string(data))
		if out, err := cmd.CombinedOutput(); err != nil {
			bail("scp config to %s: %v\n  %s", host, err, string(out))
		}
		fmt.Printf("Config deployed to %s:%s\n", host, dest)
	}
}

// ── Task ──

func taskCmd(args []string) {
	if len(args) < 1 {
		bail("Usage: vaked-cli task <list|run> [args]")
	}
	switch args[0] {
	case "list":
		requireRepo()
		out, err := execInRepo("task", "--list").Output()
		if err != nil {
			bail("task not found: install from https://taskfile.dev")
		}
		fmt.Print(string(out))
	case "run":
		if len(args) < 2 {
			bail("Usage: vaked-cli task run <name> [-- args...]")
		}
		requireRepo()
		args := []string{args[1]}
		args = append(args, args[2:]...)
		cmd := execInRepo("task", args...)
		cmd.Stdout = os.Stdout
		cmd.Stderr = os.Stderr
		cmd.Stdin = os.Stdin
		if err := cmd.Run(); err != nil {
			os.Exit(1)
		}
	default:
		bail("unknown task subcommand: %s", args[0])
	}
}

// ── Deploy ──

func deployCmd(args []string) {
	if len(args) < 1 {
		bail("Usage: vaked-cli deploy <dev|lang|docs|all>")
	}
	switch args[0] {
	case "dev":
		wranglerDeploy("deploy/vaked.dev", "vaked-dev")
	case "lang":
		wranglerDeploy("site", "vaked-lang")
	case "docs":
		deployDocs()
	case "all":
		wranglerDeploy("deploy/vaked.dev", "vaked-dev")
		wranglerDeploy("site", "vaked-lang")
	default:
		bail("unknown deploy target: %s", args[0])
	}
}

// ── Docs ──

func docsCmd(args []string) {
	if len(args) < 1 {
		bail("Usage: vaked-cli docs <gen|deploy|all>")
	}
	switch args[0] {
	case "gen":
		docsGen()
	case "deploy":
		deployDocs()
	case "all":
		docsGen()
		wranglerDeploy("site", "vaked-lang")
	default:
		bail("unknown docs subcommand: %s", args[0])
	}
}

func docsGen() {
	requireRepo()
	fmt.Println("Autogenerating docs from markdown…")
	cmd := execInRepo("python3",
		filepath.Join(repoRoot, "tools/docs-autogen.py"),
		"--source", filepath.Join(repoRoot, "docs"),
		"--output", filepath.Join(repoRoot, "site/docs"))
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		bail("docs gen failed: %v", err)
	}
	fmt.Println("Docs generated.")
}

func deployDocs() {
	docsGen()
	wranglerDeploy("site", "vaked-lang")
}

// ── Cloudflare ──

func cfCmd(args []string) {
	if len(args) < 1 {
		bail("Usage: vaked-cli cf <zones|dns|status> [zone]")
	}
	requireCF()
	switch args[0] {
	case "zones":
		cfZones()
	case "dns":
		if len(args) < 2 {
			bail("Usage: vaked-cli cf dns <zone-name>")
		}
		cfDNS(args[1])
	case "status":
		cfStatus()
	default:
		bail("unknown cf subcommand: %s", args[0])
	}
}

func cfZones() {
	data, err := cfAPI("/zones?per_page=50")
	if err != nil {
		bail("API call failed: %v", err)
	}
	var resp struct {
		Result []struct {
			Name   string      `json:"name"`
			Plan   struct{ Name string } `json:"plan"`
			Status string      `json:"status"`
		} `json:"result"`
	}
	if err := json.Unmarshal(data, &resp); err != nil {
		bail("parse error: %v", err)
	}
	fmt.Println("Cloudflare Zones:")
	for _, z := range resp.Result {
		fmt.Printf("  %-25s %-15s %s\n", z.Name, z.Plan.Name, z.Status)
	}
}

func cfDNS(zoneName string) {
	data, err := cfAPI("/zones?name=" + zoneName)
	if err != nil {
		bail("API call failed: %v", err)
	}
	var zr struct {
		Result []struct{ Id string } `json:"result"`
	}
	json.Unmarshal(data, &zr)
	if len(zr.Result) == 0 {
		bail("zone %q not found", zoneName)
	}
	data, err = cfAPI("/zones/" + zr.Result[0].Id + "/dns_records?per_page=100")
	if err != nil {
		bail("DNS fetch failed: %v", err)
	}
	var dr struct {
		Result []struct {
			Name    string `json:"name"`
			Type    string `json:"type"`
			Content string `json:"content"`
			Proxied bool   `json:"proxied"`
		} `json:"result"`
	}
	if err := json.Unmarshal(data, &dr); err != nil {
		bail("parse error: %v", err)
	}
	fmt.Printf("DNS records for %s:\n", zoneName)
	for _, r := range dr.Result {
		p := "  "
		if r.Proxied {
			p = " P"
		}
		fmt.Printf("  %s%s %-40s → %s\n", r.Type, p, r.Name, r.Content)
	}
}

func cfStatus() {
	fmt.Println("=== Cloudflare Quick Health ===")
	if data, err := cfAPI("/zones?per_page=50"); err == nil {
		var zr struct {
			Result []struct{ Name string } `json:"result"`
		}
		if json.Unmarshal(data, &zr) == nil {
			fmt.Printf("  Zones:            %d\n", len(zr.Result))
			for _, z := range zr.Result {
				fmt.Printf("                     %s\n", z.Name)
			}
		}
	}
	if cf.accountID != "" {
		if data, err := cfAPI("/accounts/" + cf.accountID + "/pages/projects?per_page=50"); err == nil {
			var pr struct {
				Result []struct{ Name string } `json:"result"`
			}
			if json.Unmarshal(data, &pr) == nil {
				fmt.Printf("  Pages projects:   %d\n", len(pr.Result))
			}
		}
	}
}

// ── walkHash (used by seal sign) ──

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

func indent(s, prefix string) string {
	lines := strings.Split(strings.TrimRight(s, "\n"), "\n")
	for i, line := range lines {
		lines[i] = prefix + line
	}
	return strings.Join(lines, "\n")
}

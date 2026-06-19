// vaked-cli — compiled CLI for Vaked development workflows.
//
// Subcommands:
//   mlir check              Validate .td files (needs mlir-tblgen)
//   mlir env                Show MLIR toolchain status
//   mlir validate <file>    Run Stage-0 pass pipeline
//   seal sign <path> <mem>  Produce a votive seal
//   seal admit <file>       Validate a seal (ADMIT/REFUSE)
//   seal verify <file>      Validate with verbose output
//   proxy discover          Scan local network for LLM endpoints (Ollama, LiteLLM, OpenRouter)
//   proxy status            Show running proxy services
//   proxy apply <file>      Deploy a proxy config to local or remote
//
// Build:
//   go build -o vaked-cli .                    # native
//   GOOS=linux GOARCH=amd64 CGO_ENABLED=0 \
//     go build -o vaked-cli-linux-x86_64 .     # cross-compile for dev-cx53
//
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

// repoRoot resolves relative to the binary location (tools/vaked-cli/ -> repo root).
var repoRoot string

func init() {
	exe, _ := os.Executable()
	real, _ := filepath.EvalSymlinks(exe)
	// Binary is at <root>/tools/vaked-cli/vaked-cli -> three Dirs up.
	repoRoot = filepath.Dir(filepath.Dir(filepath.Dir(real)))
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintf(os.Stderr, "Usage: vaked-cli <mlir|seal> <subcommand> [args]\n")
		os.Exit(1)
	}

	switch os.Args[1] {
	case "mlir":
		mlirCmd(os.Args[2:])
	case "seal":
		sealCmd(os.Args[2:])
	case "proxy":
		proxyCmd(os.Args[2:])
	default:
		fmt.Fprintf(os.Stderr, "unknown command: %s (use mlir, seal, or proxy)\n", os.Args[1])
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
			fmt.Fprintln(os.Stderr, "Usage: vaked-cli mlir validate <file.vaked>")
			os.Exit(1)
		}
		mlirValidate(args[1])
	default:
		fmt.Fprintf(os.Stderr, "unknown mlir subcommand: %s\n", args[0])
		os.Exit(1)
	}
}

func mlirCheck() {
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
		if r.err == nil {
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
	// Resolve file path: use as-is if absolute, otherwise resolve from CWD.
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
		Workflows []struct {
			Name         string   `json:"name"`
			Depth        int      `json:"depth"`
			CriticalPath []string `json:"criticalPath"`
			Steps        []string `json:"steps"`
			Edges        []struct {
				From string `json:"from"`
				To   string `json:"to"`
			} `json:"edges"`
			WALFrames []interface{} `json:"walFrames"`
		} `json:"workflows"`
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

	// Re-emit as clean JSON
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	enc.Encode(result)

	if result.Status == "FAIL" {
		os.Exit(1)
	}
}

// ========================================================================== //
// Seal subcommands (RFC 0007)
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
	Vaked        SealMeta    `json:"vaked"`
	Membrane     string      `json:"membrane"`
	ClosureHash  string      `json:"closure_hash"`
	TopologyEpoch int        `json:"topology_epoch"`
	GeneratedAt  string      `json:"generated_at"`
	Signature    SealSig     `json:"signature"`
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
	// Compute closure hash
	var closureHash string
	if len(pathOrHash) == 64 {
		if _, err := hex.DecodeString(pathOrHash); err == nil {
			closureHash = strings.ToLower(pathOrHash)
		}
	}
	if closureHash == "" {
		h := sha256.New()
		walkHash(pathOrHash, h)
		closureHash = hex.EncodeToString(h.Sum(nil))
	}

	payload := map[string]interface{}{
		"vaked":          SealMeta{Schema: "votive-seal", Version: "1"},
		"membrane":       membrane,
		"closure_hash":   closureHash,
		"topology_epoch": epoch,
		"generated_at":   time.Now().UTC().Format("2006-01-02T15:04:05Z"),
	}

	// Sign (HMAC-SHA256 placeholder — no liboqs dependency in Go)
	canon, _ := json.Marshal(payload)
	mac := hmac.New(sha256.New, make([]byte, 32))
	mac.Write(canon)
	sig := mac.Sum(nil)

	seal := VotiveSeal{
		Vaked:        SealMeta{Schema: "votive-seal", Version: "1"},
		Membrane:     membrane,
		ClosureHash:  closureHash,
		TopologyEpoch: epoch,
		GeneratedAt:  time.Now().UTC().Format("2006-01-02T15:04:05Z"),
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
// Proxy subcommands — discover, status, apply
// ========================================================================== //

func proxyCmd(args []string) {
	if len(args) < 1 {
		fmt.Fprintln(os.Stderr, "Usage: vaked-cli proxy <discover|status|apply> [args]")
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

	// 1. Local Ollama
	c := exec.Command("ollama", "list")
	if out, err := c.Output(); err == nil {
		results = append(results, fmt.Sprintf("Ollama (localhost:11434):\n  %s", indentBlock(string(out), "  ")))
	} else {
		results = append(results, "Ollama: not running on localhost:11434")
	}

	// 2. Check common ports for LiteLLM proxy
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

	// 3. Check for remote dev-cx53 endpoints (if on tailscale)
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
		// Count files and estimate size
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

	// Check remote dev-cx53
	c := exec.Command("ssh", "dev@dev-cx53",
		"du -sh ~/.vaked/llmproxy 2>/dev/null; echo '---'; du -sh ~/.ollama/models 2>/dev/null; echo '---'; du -sh ~/.cache/litellm 2>/dev/null || true",
	)
	if out, err := c.Output(); err == nil {
		fmt.Printf("\n  Remote dev-cx53:\n%s", indentBlock(string(out), "    "))
	}
}

func proxyStatus() {
	// Check what's listening on proxy-related ports
	ports := []string{"11434", "4000", "8080", "3000"}
	fmt.Println("=== LLM proxy services ===")
	for _, port := range ports {
		ep := fmt.Sprintf("http://localhost:%s/health", port)
		r := httpGet(ep)
		if r != "" {
			fmt.Printf("  port %s: RUNNING\n", port)
		} else {
			// Check if anything at all is listening
			c := exec.Command("lsof", "-i", fmt.Sprintf(":%s", port), "-sTCP:LISTEN", "-P", "-n")
			if out, err := c.Output(); err == nil && len(out) > 0 {
				lines := strings.Split(strings.TrimSpace(string(out)), "\n")
				if len(lines) > 1 {
					proc := strings.Fields(lines[1])
					if len(proc) > 1 {
						fmt.Printf("  port %s: LISTEN (%s)\n", port, proc[0])
					} else {
						fmt.Printf("  port %s: LISTEN\n", port)
					}
				}
			} else {
				fmt.Printf("  port %s: CLOSED\n", port)
			}
		}
	}
}

func proxyApply(configPath, host string) {
	// Read the proxy config
	data, err := os.ReadFile(configPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "cannot read config: %v\n", err)
		os.Exit(1)
	}

	if host == "localhost" || host == "local" {
		// Local deploy — write config and restart proxy
		dest := "deploy/llmproxy/proxy-mesh.yaml"
		if err := os.WriteFile(dest, data, 0644); err != nil {
			fmt.Fprintf(os.Stderr, "write config: %v\n", err)
			os.Exit(1)
		}
		fmt.Printf("Config written to %s\n", dest)
		fmt.Println("To start: litellm --config deploy/llmproxy/proxy-mesh.yaml --port 4000")
	} else {
		// Remote deploy via scp + ssh
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
	out []byte
	err []byte
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

func walkHash(path string, h io.Writer) {
	info, err := os.Stat(path)
	if err != nil {
		return
	}
	if !info.IsDir() {
		data, _ := os.ReadFile(path)
		h.Write(data)
		return
	}
	filepath.Walk(path, func(p string, fi os.FileInfo, err error) error {
		if err == nil && !fi.IsDir() {
			data, _ := os.ReadFile(p)
			h.Write(data)
		}
		return nil
	})
}

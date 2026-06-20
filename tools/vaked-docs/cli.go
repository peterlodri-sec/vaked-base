// Vaked Docs — CLI subcommands for register and search.
// Connects to the vaked-docs HTTP server.
// GENESIS_SEAL: 7c242080
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"
)

// DefaultServerURL is the default vaked-docs server address.
const DefaultServerURL = "http://localhost:9845"

// GetServerURL returns the server URL from env or default.
func GetServerURL() string {
	if u := os.Getenv("VAKED_DOCS_URL"); u != "" {
		return strings.TrimRight(u, "/")
	}
	return DefaultServerURL
}

// ── CLI dispatch ──────────────────────────────────────────────

// RunCLI dispatches to the appropriate subcommand based on os.Args.
// Returns true if a CLI command was handled (meaning don't start the server).
func RunCLI() bool {
	if len(os.Args) < 2 {
		return false // no subcommand — run server
	}

	switch os.Args[1] {
	case "register":
		return runRegister(os.Args[2:])
	case "search":
		return runSearch(os.Args[2:])
	case "server", "serve":
		return false // explicit server mode
	case "-h", "--help", "help":
		printHelp()
		return true
	default:
		return false
	}
}

// printHelp prints CLI usage information.
func printHelp() {
	fmt.Print(`Vaked Docs — deterministic documentation index. GENESIS_SEAL: 7c242080

Usage:
  vaked-docs                   Start the HTTP server (default)
  vaked-docs server            Start the HTTP server (explicit)
  vaked-docs register <url> [version]  Register and crawl a repo
  vaked-docs search <query>    Search indexed documentation
  vaked-docs help              Show this help

Environment:
  VAKED_DOCS_PORT  HTTP server port (default: 9845)
  VAKED_DOCS_URL   Server URL for CLI mode (default: http://localhost:9845)
  GITHUB_TOKEN     GitHub API token for higher rate limits
`)
}

// runRegister handles "vaked-docs register <url> [version]".
func runRegister(args []string) bool {
	if len(args) < 1 {
		fmt.Fprintln(os.Stderr, "Usage: vaked-docs register <url> [version]")
		os.Exit(1)
	}

	repoURL := args[0]
	version := "latest"
	if len(args) >= 2 {
		version = args[1]
	}

	serverURL := GetServerURL()

	// POST /register
	body := map[string]string{
		"url":     repoURL,
		"version": version,
	}

	// Extract owner/name for ID
	owner, repo, err := ParseRepoURL(repoURL)
	if err == nil {
		body["id"] = owner + "/" + repo
	}

	data, _ := json.Marshal(body)
	resp, err := http.Post(serverURL+"/register", "application/json", bytes.NewReader(data))
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error connecting to server at %s: %v\n", serverURL, err)
		os.Exit(1)
	}
	defer resp.Body.Close()

	respBody, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 400 {
		fmt.Fprintf(os.Stderr, "Server error %d: %s\n", resp.StatusCode, string(respBody))
		os.Exit(1)
	}

	var result map[string]interface{}
	json.Unmarshal(respBody, &result)
	fmt.Printf("Registered: %s\n", prettyJSON(result))

	// Now crawl — POST to a crawl endpoint
	// We do this via the register handler which now triggers crawling
	fmt.Println("⏳ Crawling documentation from GitHub...")

	// Fetch directly (CLI-side crawl for progress visibility)
	ref := ""
	if version != "" && version != "latest" {
		ref = version
	}
	crawler := NewCrawler(os.Getenv("GITHUB_TOKEN"), ref)
	entries, err := crawler.FetchCrawl(owner, repo)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Warning: crawl failed: %v\n", err)
		fmt.Println("Package registered but not yet indexed. Crawl manually or wait for background indexing.")
		return true
	}

	fmt.Printf("📄 Fetched %d documentation entries\n", len(entries))

	// Index and store
	storeDocs(owner+"/"+repo, version, entries)
	fmt.Println("✅ Indexed successfully")
	return true
}

// runSearch handles "vaked-docs search <query>".
func runSearch(args []string) bool {
	if len(args) < 1 {
		fmt.Fprintln(os.Stderr, "Usage: vaked-docs search <query>")
		os.Exit(1)
	}

	query := strings.Join(args, " ")
	serverURL := GetServerURL()

	// GET /search?q=...
	u := fmt.Sprintf("%s/search?q=%s", serverURL, url.QueryEscape(query))
	resp, err := http.Get(u)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error connecting to server at %s: %v\n", serverURL, err)
		os.Exit(1)
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 400 {
		fmt.Fprintf(os.Stderr, "Server error %d: %s\n", resp.StatusCode, string(body))
		os.Exit(1)
	}

	// Try to parse as ranked results
	var rankedResp struct {
		Query   string       `json:"query"`
		Results []RankResult `json:"results"`
		Count   int          `json:"count"`
	}

	if err := json.Unmarshal(body, &rankedResp); err == nil && len(rankedResp.Results) > 0 {
		fmt.Printf("Search results for %q (%d hits):\n\n", rankedResp.Query, rankedResp.Count)
		for i, r := range rankedResp.Results {
			fmt.Printf("%d. [%s] %s (score: %.4f)\n", i+1, r.PackageID, r.Query, r.Score)
		}
		return true
	}

	// Fallback: parse as legacy results
	var legacyResp struct {
		Query   string     `json:"query"`
		Results []DocEntry `json:"results"`
		Count   int        `json:"count"`
	}

	if err := json.Unmarshal(body, &legacyResp); err == nil {
		fmt.Printf("Search results for %q (%d hits):\n\n", legacyResp.Query, legacyResp.Count)
		for i, r := range legacyResp.Results {
			for _, s := range r.Snippets {
				title := s.Title
				if title == "" {
					title = "(no title)"
				}
				fmt.Printf("%d. [%s] %s\n", i+1, r.PackageID, title)
			}
		}
		return true
	}

	// Raw dump
	fmt.Println(string(body))
	return true
}

// prettyJSON formats JSON for display.
func prettyJSON(v interface{}) string {
	data, _ := json.MarshalIndent(v, "", "  ")
	return string(data)
}

// storeDocs stores crawled documentation entries and indexes them.
func storeDocs(packageID, version string, entries []DocEntry) {
	mu.Lock()
	defer mu.Unlock()

	now := time.Now().UTC().Format(time.RFC3339)

	// Register or update the package
	if pkg, ok := pkgs[packageID]; ok {
		pkg.UpdatedAt = now
		if version != "" && version != "latest" {
			pkg.Version = version
		}
	} else {
		pkgs[packageID] = &Package{
			ID:        packageID,
			Version:   version,
			UpdatedAt: now,
		}
	}

	// Store entries under versioned key
	storeKey := packageID + "@" + version
	docs[storeKey] = entries
	for range entries {
		docCount++
	}

	// Build TF-IDF index for BM25 search
	if docIndexer != nil {
		for _, e := range entries {
			for _, s := range e.Snippets {
				content := s.Code
				if s.Content != "" {
					if content != "" {
						content += "\n" + s.Content
					} else {
						content = s.Content
					}
				}
				if content != "" {
					docIndexer.AddDocument(packageID, e.Query, content)
				}
			}
		}
		// Rebuild BM25 scorer with updated average doc length
		docScorerPtr.Store(NewBM25Scorer(docIndexer))
	}

	log.Printf("indexed %s: %d entries", storeKey, len(entries))
}

// Vaked Docs — public, deterministic documentation index.
// Context7 alternative. Open source. Self-hostable.
// GENESIS_SEAL: 7c242080
package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"
)

const (
	PORT       = 9845
	GENESIS    = "7c242080"
	MAX_DOCS   = 100000
)

// ── Package registry ──────────────────────────────────────────

type Package struct {
	ID          string   `json:"id"`          // e.g. "ziglang/zig"
	Version     string   `json:"version"`     // e.g. "0.16.0"
	Name        string   `json:"name"`
	Description string   `json:"description"`
	URL         string   `json:"url"`         // repo URL
	Queries     []string `json:"queries"`     // pre-indexed queries
	UpdatedAt   string   `json:"updated_at"`
}

type DocSnippet struct {
	Code    string `json:"code,omitempty"`
	Content string `json:"content,omitempty"`
	Title   string `json:"title,omitempty"`
}

type DocEntry struct {
	PackageID string       `json:"package_id"`
	Query     string       `json:"query"`
	Snippets  []DocSnippet `json:"snippets"`
	FetchedAt string       `json:"fetched_at"`
}

// ── In-memory store ───────────────────────────────────────────

var (
	mu        sync.RWMutex
	pkgs      = make(map[string]*Package)
	docs      = make(map[string][]DocEntry) // package_id@version -> entries
	docCount  int
	docIndexer *TFIDFIndexer
	docScorer  *BM25Scorer
)

// ── API handlers ──────────────────────────────────────────────

func healthHandler(w http.ResponseWriter, r *http.Request) {
	mu.RLock()
	pkgCount := len(pkgs)
	mu.RUnlock()

	terms, idxDocs := 0, 0
	if docIndexer != nil {
		terms, idxDocs = docIndexer.IndexSize()
	}

	json.NewEncoder(w).Encode(map[string]interface{}{
		"status":  "ok",
		"genesis": GENESIS,
		"packages": pkgCount,
		"docs":    docCount,
		"indexed": idxDocs,
		"terms":   terms,
	})
}

func registerHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "POST required", http.StatusMethodNotAllowed)
		return
	}

	var pkg Package
	if err := json.NewDecoder(r.Body).Decode(&pkg); err != nil {
		http.Error(w, "invalid JSON", http.StatusBadRequest)
		return
	}

	if pkg.ID == "" && pkg.URL == "" {
		http.Error(w, "id or url required", http.StatusBadRequest)
		return
	}

	// Derive ID from URL if not provided
	if pkg.ID == "" {
		owner, repo, err := ParseRepoURL(pkg.URL)
		if err == nil {
			pkg.ID = owner + "/" + repo
		} else {
			http.Error(w, "could not parse repo URL; provide id", http.StatusBadRequest)
			return
		}
	}

	if pkg.Version == "" {
		pkg.Version = "latest"
	}
	pkg.UpdatedAt = time.Now().UTC().Format(time.RFC3339)

	// Attempt to crawl if URL provided
	entries := []DocEntry{}
	if pkg.URL != "" {
		owner, repo, err := ParseRepoURL(pkg.URL)
		if err == nil {
			crawler := NewCrawler(os.Getenv("GITHUB_TOKEN"))
			var crawlErr error
			entries, crawlErr = crawler.FetchCrawl(owner, repo)
			if crawlErr != nil {
				log.Printf("crawl warning for %s: %v", pkg.ID, crawlErr)
			}
		}
	}

	storeKey := pkg.ID + "@" + pkg.Version

	mu.Lock()
	pkgs[pkg.ID] = &pkg
	if len(entries) > 0 {
		docs[storeKey] = entries
		for range entries {
			docCount++
		}
		// Index for BM25
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
						docIndexer.AddDocument(pkg.ID, e.Query, content)
					}
				}
			}
			docScorer = NewBM25Scorer(docIndexer)
		}
	}
	mu.Unlock()

	log.Printf("registered: %s@%s (%d entries)", pkg.ID, pkg.Version, len(entries))

	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status":     "registered",
		"id":         pkg.ID,
		"version":    pkg.Version,
		"entries":    len(entries),
	})
}

func docsHandler(w http.ResponseWriter, r *http.Request) {
	// GET /docs/:pkg@version?q=query
	// version is optional: /docs/pkg  or  /docs/pkg@version
	pkgID := strings.TrimPrefix(r.URL.Path, "/docs/")
	if pkgID == "" {
		http.Error(w, "package ID required", http.StatusBadRequest)
		return
	}

	query := r.URL.Query().Get("q")

	// Parse version from pkg@version syntax
	version := "latest"
	if idx := strings.LastIndex(pkgID, "@"); idx > 0 && strings.Contains(pkgID[idx+1:], ".") {
		version = pkgID[idx+1:]
		pkgID = pkgID[:idx]
	}

	// Try exact match first, then fall back to latest
	storeKey := pkgID + "@" + version

	mu.RLock()
	entries, ok := docs[storeKey]
	if !ok && version != "latest" {
		// Try without version
		entries, ok = docs[pkgID+"@latest"]
	}
	mu.RUnlock()

	if !ok {
		http.Error(w, fmt.Sprintf("package not found or not indexed: %s@%s", pkgID, version), http.StatusNotFound)
		return
	}

	if query != "" {
		// Try BM25 first if indexer is available
		if docScorer != nil {
			ranked := docScorer.Search(query, 20)
			var filtered []DocEntry
			for _, r := range ranked {
				if r.PackageID == pkgID {
					// Find the matching DocEntry
					for _, e := range entries {
						if e.Query == r.Query {
							filtered = append(filtered, e)
							break
						}
					}
				}
			}
			if len(filtered) > 0 {
				json.NewEncoder(w).Encode(map[string]interface{}{
					"package": pkgID + "@" + version,
					"version": version,
					"query":   query,
					"results": filtered,
					"count":   len(filtered),
				})
				return
			}
		}

		// Fallback: simple keyword search
		var results []DocEntry
		lower := strings.ToLower(query)
		for _, e := range entries {
			for _, s := range e.Snippets {
				content := s.Code + s.Content
				if strings.Contains(strings.ToLower(content), lower) {
					results = append(results, e)
					break
				}
			}
		}
		entries = results
	}

	json.NewEncoder(w).Encode(map[string]interface{}{
		"package": pkgID + "@" + version,
		"version": version,
		"query":   query,
		"results": entries,
		"count":   len(entries),
	})
}

func listHandler(w http.ResponseWriter, r *http.Request) {
	mu.RLock()
	defer mu.RUnlock()

	type pkgInfo struct {
		ID        string `json:"id"`
		Version   string `json:"version"`
		URL       string `json:"url,omitempty"`
		UpdatedAt string `json:"updated_at"`
		DocCount  int    `json:"doc_count"`
	}

	infos := make([]pkgInfo, 0, len(pkgs))
	for id, p := range pkgs {
		storeKey := id + "@" + p.Version
		dc := len(docs[storeKey])
		infos = append(infos, pkgInfo{
			ID:        id,
			Version:   p.Version,
			URL:       p.URL,
			UpdatedAt: p.UpdatedAt,
			DocCount:  dc,
		})
	}

	json.NewEncoder(w).Encode(map[string]interface{}{
		"packages": infos,
		"count":    len(infos),
	})
}

func searchHandler(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query().Get("q")
	if query == "" {
		http.Error(w, "?q= required", http.StatusBadRequest)
		return
	}

	// Try BM25 first
	if docScorer != nil {
		ranked := docScorer.Search(query, 20)
		json.NewEncoder(w).Encode(map[string]interface{}{
			"query":   query,
			"results": ranked,
			"count":   len(ranked),
		})
		return
	}

	// Fallback: simple substring search
	lower := strings.ToLower(query)
	var results []DocEntry

	mu.RLock()
	for pkgID, entries := range docs {
		for _, e := range entries {
			for _, s := range e.Snippets {
				content := strings.ToLower(s.Code + s.Content)
				if strings.Contains(content, lower) {
					e.PackageID = pkgID
					results = append(results, e)
					break
				}
			}
		}
	}
	mu.RUnlock()

	if len(results) > 20 {
		results = results[:20]
	}

	json.NewEncoder(w).Encode(map[string]interface{}{
		"query":   query,
		"results": results,
		"count":   len(results),
	})
}

// ── Seed data — pre-indexed Vaked swarm libraries ──────────────

func seedDocs() {
	entries := []DocEntry{
		{
			PackageID: "ziglang/zig",
			Query:     "std.Build API",
			FetchedAt: "2026-06-18T00:00:00Z",
			Snippets: []DocSnippet{
				{Code: "const std = @import(\"std\");\npub fn build(b: *std.Build) void {\n    const exe = b.addExecutable(.{\n        .name = \"myapp\",\n        .root_source_file = b.path(\"src/main.zig\"),\n        .target = target,\n        .optimize = optimize,\n    });\n    b.installArtifact(exe);\n}", Title: "std.Build basic setup"},
				{Content: "std.Build is the Zig build system. Use b.addExecutable, b.addLibrary, b.addTest to create build artifacts. The build function receives a *std.Build and mutates the build graph. Target and optimize options come from b.standardTargetOptions and b.standardOptimizeOption.", Title: "Build system overview"},
			},
		},
		{
			PackageID: "ziglang/zig",
			Query:     "ArrayListUnmanaged",
			FetchedAt: "2026-06-18T00:00:00Z",
			Snippets: []DocSnippet{
				{Code: "var list: std.ArrayListUnmanaged(u8) = .{ .items = &.{}, .capacity = 0 };\ndefer list.deinit(allocator);\ntry list.append(allocator, 42);", Title: "ArrayListUnmanaged init"},
				{Content: "Zig 0.16: std.ArrayList is removed. Use std.ArrayListUnmanaged. Initialize with .{ .items = &.{}, .capacity = 0 }. No .init() method. Pass allocator to every method.", Title: "ArrayListUnmanaged migration"},
			},
		},
		{
			PackageID: "nixos/nixpkgs",
			Query:     "buildRustPackage",
			FetchedAt: "2026-06-18T00:00:00Z",
			Snippets: []DocSnippet{
				{Code: `{ buildRustPackage, fetchFromGitHub }:
buildRustPackage rec {
  pname = "myapp";
  version = "0.1.0";
  src = fetchFromGitHub { owner = "me"; repo = "myapp"; hash = "sha256-..."; };
  cargoHash = "sha256-...";
}`, Title: "buildRustPackage example"},
			},
		},
		{
			PackageID: "tauri-apps/tauri",
			Query:     "plugin system",
			FetchedAt: "2026-06-18T00:00:00Z",
			Snippets: []DocSnippet{
				{Code: "use tauri::plugin::{Builder, TauriPlugin};\n\npub fn init() -> TauriPlugin {\n    Builder::new(\"myplugin\").build()\n}", Title: "Tauri plugin builder"},
			},
		},
	}

	mu.Lock()
	for _, e := range entries {
		storeKey := e.PackageID + "@latest"
		docs[storeKey] = append(docs[storeKey], e)
		docCount++
		// Index for BM25
		if docIndexer != nil {
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
					docIndexer.AddDocument(e.PackageID, e.Query, content)
				}
			}
		}
	}
	mu.Unlock()

	// Register seed packages
	for _, id := range []string{"ziglang/zig", "nixos/nixpkgs", "tauri-apps/tauri"} {
		pkgs[id] = &Package{ID: id, Version: "latest", UpdatedAt: "2026-06-18T00:00:00Z"}
	}

	// Rebuild scorer
	if docIndexer != nil {
		docScorer = NewBM25Scorer(docIndexer)
	}
}

// ── Main ──────────────────────────────────────────────────────

func main() {
	port := PORT
	if p := os.Getenv("VAKED_DOCS_PORT"); p != "" {
		fmt.Sscanf(p, "%d", &port)
	}

	// Check for CLI subcommands before starting the server
	if RunCLI() {
		return
	}

	// Initialize the TF-IDF indexer for BM25 search
	docIndexer = NewIndexer()

	seedDocs()

	http.HandleFunc("/health", healthHandler)
	http.HandleFunc("/register", registerHandler)
	http.HandleFunc("/docs/", docsHandler)
	http.HandleFunc("/list", listHandler)
	http.HandleFunc("/search", searchHandler)

	terms, idxDocs := docIndexer.IndexSize()
	log.Printf("vaked-docs :%d · genesis %s · %d pkgs · %d docs · %d indexed · %d terms",
		port, GENESIS, len(pkgs), docCount, idxDocs, terms)
	log.Fatal(http.ListenAndServe(fmt.Sprintf(":%d", port), nil))
}

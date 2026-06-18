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
	mu       sync.RWMutex
	pkgs     = make(map[string]*Package)
	docs     = make(map[string][]DocEntry) // package_id -> entries
	docCount int
)

// ── API handlers ──────────────────────────────────────────────

func healthHandler(w http.ResponseWriter, r *http.Request) {
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status":   "ok",
		"genesis":  GENESIS,
		"packages": len(pkgs),
		"docs":     docCount,
	})
}

func registerHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "POST only", http.StatusMethodNotAllowed)
		return
	}

	var pkg Package
	if err := json.NewDecoder(r.Body).Decode(&pkg); err != nil {
		http.Error(w, "invalid JSON: "+err.Error(), http.StatusBadRequest)
		return
	}

	if pkg.ID == "" || pkg.URL == "" {
		http.Error(w, "id and url required", http.StatusBadRequest)
		return
	}

	if pkg.Version == "" {
		pkg.Version = "latest"
	}
	pkg.UpdatedAt = time.Now().UTC().Format(time.RFC3339)

	mu.Lock()
	pkgs[pkg.ID] = &pkg
	mu.Unlock()

	log.Printf("registered: %s@%s", pkg.ID, pkg.Version)

	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(map[string]string{
		"status": "registered",
		"id":     pkg.ID,
	})
}

func docsHandler(w http.ResponseWriter, r *http.Request) {
	// GET /docs/:pkg?q=query
	pkgID := strings.TrimPrefix(r.URL.Path, "/docs/")
	if pkgID == "" {
		http.Error(w, "package ID required", http.StatusBadRequest)
		return
	}

	query := r.URL.Query().Get("q")

	mu.RLock()
	entries, ok := docs[pkgID]
	mu.RUnlock()

	if !ok {
		http.Error(w, "package not found or not indexed", http.StatusNotFound)
		return
	}

	if query != "" {
		// Simple keyword search
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
		"package": pkgID,
		"query":   query,
		"results": entries,
	})
}

func listHandler(w http.ResponseWriter, r *http.Request) {
	mu.RLock()
	defer mu.RUnlock()

	ids := make([]string, 0, len(pkgs))
	for id := range pkgs {
		ids = append(ids, id)
	}

	json.NewEncoder(w).Encode(map[string]interface{}{
		"packages": ids,
		"count":    len(ids),
	})
}

func searchHandler(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query().Get("q")
	if query == "" {
		http.Error(w, "?q= required", http.StatusBadRequest)
		return
	}

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
		docs[e.PackageID] = append(docs[e.PackageID], e)
		docCount++
	}
	mu.Unlock()

	// Register seed packages
	for _, id := range []string{"ziglang/zig", "nixos/nixpkgs", "tauri-apps/tauri"} {
		pkgs[id] = &Package{ID: id, Version: "latest", UpdatedAt: "2026-06-18T00:00:00Z"}
	}
}

// ── Main ──────────────────────────────────────────────────────

func main() {
	port := PORT
	if p := os.Getenv("VAKED_DOCS_PORT"); p != "" {
		fmt.Sscanf(p, "%d", &port)
	}

	seedDocs()

	http.HandleFunc("/health", healthHandler)
	http.HandleFunc("/register", registerHandler)
	http.HandleFunc("/docs/", docsHandler)
	http.HandleFunc("/list", listHandler)
	http.HandleFunc("/search", searchHandler)

	log.Printf("vaked-docs :%d · genesis %s · %d pkgs · %d docs", port, GENESIS, len(pkgs), docCount)
	log.Fatal(http.ListenAndServe(fmt.Sprintf(":%d", port), nil))
}

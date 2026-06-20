package repomap

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/usewhale/whale/internal/agent"
	"github.com/usewhale/whale/internal/plugins"
)

const PluginID = "repomap"

// ── Plugin ────────────────────────────────────────────────────────────────

type Plugin struct {
	cache     *Cache
	graph     *Graph
	mu        sync.RWMutex
	root      string
	ready     bool
	lastBuild time.Time
}

func (p *Plugin) Manifest() plugins.Manifest {
	return plugins.Manifest{
		ID:          PluginID,
		Name:        "Repo Map",
		Version:     "0.1.0",
		Description: "Builds a dependency graph of the workspace and injects it into the LLM context.",
		Authors:     []string{"Vaked"},
		License:     "MIT",
		Capabilities: []plugins.Capability{
			plugins.CapabilityStartupContext,
			plugins.CapabilityHooks,
		},
		Permissions: []plugins.Permission{
			plugins.PermissionReadWorkspace,
		},
	}
}

// ── StartupContextProvider ─────────────────────────────────────────────────

func (p *Plugin) StartupContext(ctx context.Context, pc plugins.Context) (string, error) {
	p.mu.RLock()
	defer p.mu.RUnlock()

	if !p.ready || p.graph == nil {
		return "", nil
	}

	var sb strings.Builder
	sb.WriteString("[REPO_MAP]\n")
	sb.WriteString(fmt.Sprintf("Files: %d  Symbols: %d  Edges: %d\n",
		len(p.graph.Files), len(p.graph.Symbols), len(p.graph.Edges)))
	sb.WriteString(p.graph.ToJSON())
	sb.WriteString("\n[/REPO_MAP]")
	return sb.String(), nil
}

// ── HookProvider ──────────────────────────────────────────────────────────

func (p *Plugin) Hooks(pc plugins.Context) []agent.HookHandler {
	return []agent.HookHandler{
		{
			Event:       agent.HookEventPostToolUse,
			Name:        "repomap.invalidate-on-write",
			Source:      "plugin:repomap",
			Description: "Invalidates cached symbols when a file is written or edited.",
			Run: func(ctx context.Context, payload agent.HookPayload) agent.HookResult {
				return p.onPostToolUse(payload)
			},
		},
		{
			Event:       agent.HookEventSessionStart,
			Name:        "repomap.build-on-start",
			Source:      "plugin:repomap",
			Description: "Builds the initial repo map when a session starts.",
			Run: func(ctx context.Context, payload agent.HookPayload) agent.HookResult {
				return p.onSessionStart()
			},
		},
	}
}

func (p *Plugin) onPostToolUse(payload agent.HookPayload) agent.HookResult {
	toolName := payload.ToolName
	switch toolName {
	case "write", "edit", "multi_edit":
		if args, ok := payload.ToolArgs.(map[string]any); ok {
			if filePath, ok := args["file_path"].(string); ok {
				relPath, err := filepath.Rel(p.root, filePath)
				if err == nil && !strings.HasPrefix(relPath, "..") {
					p.cache.Invalidate(relPath)
					go p.rebuildFile(relPath)
				}
			}
		}
	}
	return agent.HookResult{Decision: agent.HookDecisionPass}
}

func (p *Plugin) onSessionStart() agent.HookResult {
	go p.buildFull()
	return agent.HookResult{Decision: agent.HookDecisionPass}
}

// ── Background build ──────────────────────────────────────────────────────

func (p *Plugin) buildFull() {
	p.mu.Lock()
	p.ready = false
	p.mu.Unlock()

	root := p.root
	var paths []string
	_ = filepath.Walk(root, func(fullPath string, info os.FileInfo, err error) error {
		if err != nil {
			return nil
		}
		if info.IsDir() {
			base := filepath.Base(fullPath)
			if strings.HasPrefix(base, ".") || base == "node_modules" || base == "target" ||
				base == ".git" || base == "zig-cache" || base == "zig-out" || base == "__pycache__" {
				return filepath.SkipDir
			}
			return nil
		}
		rel, _ := filepath.Rel(root, fullPath)
		ext := filepath.Ext(rel)
		if detectExt(ext) {
			paths = append(paths, rel)
		}
		return nil
	})

	graph, err := BuildGraphSIMD(root, paths, p.cache)
	if err != nil {
		return
	}

	p.mu.Lock()
	p.graph = graph
	p.lastBuild = time.Now()
	p.ready = true
	p.mu.Unlock()
}

func (p *Plugin) rebuildFile(relPath string) {
	fullPath := filepath.Join(p.root, relPath)
	src, err := os.ReadFile(fullPath)
	if err != nil {
		return
	}

	ext := filepath.Ext(relPath)
	if !detectExt(ext) {
		return
	}

	syms := ExtractSymbolsSIMD(relPath, src)
	_ = p.cache.Put(relPath, syms)

	p.mu.Lock()
	defer p.mu.Unlock()

	// Remove old symbols for this file
	for key, sym := range p.graph.Symbols {
		if sym.File == relPath {
			delete(p.graph.Symbols, key)
		}
	}
	for _, sym := range syms {
		p.graph.AddSymbol(sym)
	}
}

// ── DoctorProvider ────────────────────────────────────────────────────────

func (p *Plugin) Doctor(ctx context.Context, pc plugins.Context) []plugins.Diagnostic {
	p.mu.RLock()
	defer p.mu.RUnlock()

	if !p.ready {
		return []plugins.Diagnostic{{
			PluginID: PluginID,
			Level:    plugins.DiagnosticWarn,
			Label:    "repo map",
			Detail:   "not yet built — will build on next session start",
		}}
	}

	return []plugins.Diagnostic{{
		PluginID: PluginID,
		Level:    plugins.DiagnosticOK,
		Label:    "repo map",
		Detail:   fmt.Sprintf("%d files, %d symbols, %d edges (built %s)",
			len(p.graph.Files), len(p.graph.Symbols), len(p.graph.Edges),
			p.lastBuild.Format(time.RFC3339)),
	}}
}

// ── Constructor ───────────────────────────────────────────────────────────

func NewPlugin(workspaceRoot string) *Plugin {
	return &Plugin{
		cache: NewCache(workspaceRoot),
		root:  workspaceRoot,
	}
}

// detectExt returns true if the extension is a supported language.
// Shared between regex and tree-sitter paths.
func detectExt(ext string) bool {
	switch ext {
	case ".go", ".py", ".zig", ".rs", ".ts", ".tsx", ".js", ".jsx", ".mjs",
		".nix", ".toml", ".yml", ".yaml", ".md":
		return true
	}
	return false
}

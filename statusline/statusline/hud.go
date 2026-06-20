// Package statusline renders a tmux-style status bar with live metrics.
// HUD = Heads-Up Display. Always visible, always updating.
// Replaces the multi-line footer with a single compact statusline.
package statusline

import (
	"fmt"
	"strings"
	"time"

	"github.com/charmbracelet/lipgloss"
)

// HUD renders the statusline. Single row. All info in one line.
type HUD struct {
	Width int

	// Left section: model info + workspace
	Model      string
	Mode       string // agent, ask, plan
	Branch     string
	CWD        string
	
	// Center section: live agent stats
	Busy        bool
	Elapsed     time.Duration
	TokenCount  int
	TokensPerSec float64
	CacheHitPct float64
	
	// Right section: system stats
	MemoryMB    int64
	CostUSD     float64
	Plugins     int
	Theme       string
	
	// AG-UI theme colors
	BgColor     lipgloss.Color
	FgColor     lipgloss.Color
	AccentColor lipgloss.Color
	DimColor    lipgloss.Color
	WarnColor   lipgloss.Color
	GoodColor   lipgloss.Color
}

// DefaultHUD returns a HUD with sensible defaults.
func DefaultHUD(width int) *HUD {
	return &HUD{
		Width:       width,
		BgColor:     lipgloss.Color("#0a0a14"),
		FgColor:     lipgloss.Color("#e0e8f5"),
		AccentColor: lipgloss.Color("#00d4ff"),
		DimColor:    lipgloss.Color("#6878a0"),
		WarnColor:   lipgloss.Color("#ffaa00"),
		GoodColor:   lipgloss.Color("#00e660"),
	}
}

// Render produces the full statusline string.
func (h HUD) Render() string {
	if h.Width <= 0 {
		return ""
	}

	left := h.renderLeft()
	center := h.renderCenter()
	right := h.renderRight()

	// Calculate widths: center gets whatever is left after left + right
	leftW := lipgloss.Width(left)
	rightW := lipgloss.Width(right)
	centerW := h.Width - leftW - rightW - 4 // 4 for padding
	if centerW < 10 {
		centerW = 10
	}

	center = lipgloss.NewStyle().
		Width(centerW).
		Align(lipgloss.Center).
		Render(center)

	// Background bar
	bar := lipgloss.NewStyle().
		Background(h.BgColor).
		Foreground(h.FgColor).
		Width(h.Width).
		Padding(0, 1).
		Render(lipgloss.JoinHorizontal(lipgloss.Left, left, center, right))

	return bar
}

func (h HUD) renderLeft() string {
	var parts []string
	
	// Model indicator
	modelStyle := lipgloss.NewStyle().Foreground(h.AccentColor).Bold(true)
	parts = append(parts, modelStyle.Render(h.Model))
	
	// Mode badge
	if h.Mode != "" && h.Mode != "agent" {
		modeStyle := lipgloss.NewStyle().
			Foreground(h.BgColor).
			Background(h.WarnColor).
			Padding(0, 1)
		parts = append(parts, modeStyle.Render(h.Mode))
	}
	
	// Branch
	if h.Branch != "" {
		branchStyle := lipgloss.NewStyle().Foreground(h.DimColor)
		parts = append(parts, branchStyle.Render("⎇ "+h.Branch))
	}
	
	return lipgloss.NewStyle().
		Foreground(h.FgColor).
		Background(h.BgColor).
		Render(strings.Join(parts, " "))
}

func (h HUD) renderCenter() string {
	if !h.Busy {
		return lipgloss.NewStyle().
			Foreground(h.DimColor).
			Render("ready")
	}

	var parts []string
	
	// Elapsed timer
	elapsed := formatDuration(h.Elapsed)
	parts = append(parts, lipgloss.NewStyle().
		Foreground(h.WarnColor).
		Render("● "+elapsed))
	
	// Token count
	if h.TokenCount > 0 {
		parts = append(parts, lipgloss.NewStyle().
			Foreground(h.FgColor).
			Render(fmt.Sprintf("%dt", h.TokenCount)))
	}
	
	// Tokens/sec
	if h.TokensPerSec > 0 {
		parts = append(parts, lipgloss.NewStyle().
			Foreground(h.GoodColor).
			Render(fmt.Sprintf("%.0f/s", h.TokensPerSec)))
	}
	
	// Cache hit rate
	if h.CacheHitPct > 0 {
		color := h.GoodColor
		if h.CacheHitPct < 50 {
			color = h.WarnColor
		}
		parts = append(parts, lipgloss.NewStyle().
			Foreground(color).
			Render(fmt.Sprintf("⎆%.0f%%", h.CacheHitPct)))
	}
	
	return lipgloss.NewStyle().
		Foreground(h.FgColor).
		Render(strings.Join(parts, " · "))
}

func (h HUD) renderRight() string {
	var parts []string
	
	// Memory
	if h.MemoryMB > 0 {
		parts = append(parts, lipgloss.NewStyle().
			Foreground(h.DimColor).
			Render(fmt.Sprintf("%dMB", h.MemoryMB)))
	}
	
	// Cost
	if h.CostUSD > 0 {
		costColor := h.DimColor
		if h.CostUSD > 0.50 {
			costColor = h.WarnColor
		}
		parts = append(parts, lipgloss.NewStyle().
			Foreground(costColor).
			Render(fmt.Sprintf("$%.4f", h.CostUSD)))
	}
	
	// Plugins
	if h.Plugins > 0 {
		parts = append(parts, lipgloss.NewStyle().
			Foreground(h.AccentColor).
			Render(fmt.Sprintf("⚙%d", h.Plugins)))
	}
	
	// Theme
	if h.Theme != "" {
		parts = append(parts, lipgloss.NewStyle().
			Foreground(h.DimColor).
			Render(h.Theme[:2]))
	}
	
	return lipgloss.NewStyle().
		Foreground(h.FgColor).
		Background(h.BgColor).
		Render(strings.Join(parts, " "))
}

func formatDuration(d time.Duration) string {
	if d < time.Second {
		return fmt.Sprintf("%dms", d.Milliseconds())
	}
	if d < time.Minute {
		return fmt.Sprintf("%.1fs", d.Seconds())
	}
	m := int(d.Minutes())
	s := int(d.Seconds()) % 60
	return fmt.Sprintf("%d:%02d", m, s)
}

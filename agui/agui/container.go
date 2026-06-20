package agui

import (
	"strings"

	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

// Container is a Bubble Tea model that renders content inside an AG-UI themed border.
// It wraps any string content and draws a thin colored border with a header bar.
type Container struct {
	Title   string
	Status  string // e.g. "running", "done", "error"
	Content string
	Theme   Theme
	Width   int
	Height  int

	vp viewport.Model
}

// NewContainer creates an AG-UI container.
func NewContainer(title, status string, width, height int) Container {
	vp := viewport.New(width, height)
	return Container{
		Title:  title,
		Status: status,
		Width:  width,
		Height: height,
		Theme:  Current,
		vp:     vp,
	}
}

// SetContent updates the container content and refreshes the viewport.
func (c *Container) SetContent(content string) {
	c.Content = content
	c.vp.SetContent(content)
	if c.Height > 0 {
		c.vp.Height = c.Height - 3 // account for header + borders
	}
}

// Init implements tea.Model.
func (c Container) Init() tea.Cmd { return nil }

// Update implements tea.Model.
func (c Container) Update(msg tea.Msg) (Container, tea.Cmd) {
	var cmd tea.Cmd
	c.vp, cmd = c.vp.Update(msg)
	return c, cmd
}

// View renders the container with AG-UI themed borders.
func (c Container) View() string {
	t := c.Theme
	w := c.Width
	if w < 10 {
		w = 40
	}

	// Header bar
	headerStyle := lipgloss.NewStyle().
		Background(t.Surface).
		Foreground(t.Accent).
		Width(w - 2).
		Padding(0, 1)

	statusColor := t.Dim
	switch c.Status {
	case "running":
		statusColor = t.Accent
	case "done":
		statusColor = lipgloss.Color("#00e660")
	case "error":
		statusColor = lipgloss.Color("#ff4444")
	}

	statusStyle := lipgloss.NewStyle().
		Background(t.Surface).
		Foreground(statusColor)

	header := headerStyle.Render(c.Title) + statusStyle.Render(" "+c.Status)

	// Content area
	contentStyle := lipgloss.NewStyle().
		Background(t.Bg).
		Foreground(t.Fg).
		Width(w - 2).
		Padding(1)

	content := contentStyle.Render(c.Content)

	// Border
	borderStyle := lipgloss.NewStyle().
		Border(lipgloss.NormalBorder()).
		BorderForeground(t.Border).
		Width(w)

	return borderStyle.Render(header + "\n" + content)
}

// ── Block renderers ──────────────────────────────────────────────────────

// RenderBlock renders a single block with AG-UI chrome.
func RenderBlock(blockType BlockType, title, content string, width int) string {
	t := Current
	icon := blockIcon(blockType)
	color := blockColor(blockType, t)

	// Compact header
	header := lipgloss.NewStyle().
		Foreground(color).
		Render(icon + " " + title)

	// Content with left border accent
	body := lipgloss.NewStyle().
		Border(lipgloss.Border{Left: "▎"}, false, false, false, true).
		BorderForeground(color).
		Padding(0, 1).
		Width(width - 2).
		Foreground(t.Fg).
		Render(content)

	return header + "\n" + body
}

// BlockType identifies the kind of content being rendered.
type BlockType int

const (
	BlockText      BlockType = iota
	BlockThinking
	BlockToolCall
	BlockToolResult
	BlockCodeDiff
	BlockPlanCard
	BlockFileTree
)

func blockIcon(bt BlockType) string {
	switch bt {
	case BlockThinking:
		return "⏳"
	case BlockToolCall:
		return "🔧"
	case BlockToolResult:
		return "📋"
	case BlockCodeDiff:
		return "Δ"
	case BlockPlanCard:
		return "📐"
	case BlockFileTree:
		return "📁"
	default:
		return "·"
	}
}

func blockColor(bt BlockType, t Theme) lipgloss.Color {
	switch bt {
	case BlockThinking:
		return t.Dim
	case BlockToolCall:
		return t.Accent
	case BlockToolResult:
		return t.Fg
	case BlockCodeDiff:
		return lipgloss.Color("#00e660")
	case BlockPlanCard:
		return lipgloss.Color("#00d4ff")
	case BlockFileTree:
		return t.Accent
	default:
		return t.Fg
	}
}

// ── Helpers ──────────────────────────────────────────────────────────────

// PadRight pads a string to the given width.
func PadRight(s string, width int) string {
	if len(s) >= width {
		return s
	}
	return s + strings.Repeat(" ", width-len(s))
}

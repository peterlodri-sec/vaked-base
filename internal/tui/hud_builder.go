package tui

import (
	"time"

	"github.com/usewhale/whale/internal/tui/statusline"
)

func (m *model) buildHUD(width int) {
	if m.hud == nil {
		m.hud = statusline.DefaultHUD(width)
	}
	h := m.hud
	h.Width = width
	h.Model = m.model
	h.Mode = m.chatMode
	h.Branch = m.gitBranch
	h.CWD = m.cwd
	h.Busy = m.busy
	if m.busy {
		h.Elapsed = time.Since(m.busySince)
	}
	h.TokenCount = m.busyTokenCount
	h.Plugins = 4
	if m.viewMode != "" {
		h.Theme = m.viewMode
	}
}

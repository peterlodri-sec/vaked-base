#!/usr/bin/env python3
# Patch render.go, model.go, model_keys.go for InfraBar integration

with open("/home/dev/whale/internal/tui/render.go") as f:
    content = f.read()

old = '\tbody := m.renderContent(mainWidth, bodyHeight)'
new = '\tinfraLine := ""\n\tif m.infraBar != nil && m.infraBar.Visible {\n\t\tinfraLine = m.infraBar.View()\n\t}\n\tbody := m.renderContent(mainWidth, bodyHeight)\n\tif infraLine != "" {\n\t\tbody = infraLine + "\\n" + body\n\t}'

content = content.replace(old, new)
with open("/home/dev/whale/internal/tui/render.go", "w") as f:
    f.write(content)

# Patch model.go
with open("/home/dev/whale/internal/tui/model.go") as f:
    content = f.read()

content = content.replace(
    'ultracode *modes.UltracodeMode',
    'ultracode *modes.UltracodeMode\n\tinfraBar *widgets.InfraBarWidget'
)
content = content.replace(
    '"github.com/usewhale/whale/internal/tui/statusline"',
    '"github.com/usewhale/whale/internal/tui/statusline"\n\t"github.com/usewhale/whale/internal/tui/widgets"'
)
content = content.replace(
    'hud:                statusline.DefaultHUD(80),',
    'hud:                statusline.DefaultHUD(80),\n\t\tinfraBar:            widgets.NewInfraBar(),'
)
with open("/home/dev/whale/internal/tui/model.go", "w") as f:
    f.write(content)

# Patch model_keys.go
with open("/home/dev/whale/internal/tui/model_keys.go") as f:
    content = f.read()

content = content.replace(
    'case "ctrl+shift+s":',
    'case "ctrl+shift+i":\n\t\t\tif m.infraBar != nil { m.infraBar.ToggleExpanded(); m.refreshLiveViewportContent() }\n\t\t\treturn nil, false, true\n\t\tcase "ctrl+shift+s":'
)
with open("/home/dev/whale/internal/tui/model_keys.go", "w") as f:
    f.write(content)

print("3 files patched")

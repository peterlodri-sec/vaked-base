#!/usr/bin/env python3
with open("/home/dev/whale/internal/tui/model_prompt.go") as f:
    content = f.read()

# 1. Add blocks import
content = content.replace(
    '"time"',
    '"time"\n\t"github.com/usewhale/whale/internal/blocks"'
)

# 2. Add /self + /ultracode interceptors  
old_intercept = '\tif strings.HasPrefix(strings.TrimSpace(value), "/reload") {\n\t\thandled, msg := m.handleReloadCommand(value)\n\t\tif handled {\n\t\t\tm.setEphemeralInfo(msg)\n\t\t\tm.input.SetValue("")\n\t\t\tm.refreshViewportContent()\n\t\t\treturn nil\n\t\t}\n\t}'
new_intercept = '\tif strings.HasPrefix(strings.TrimSpace(value), "/self") {\n\t\tm.setEphemeralInfo(handleSelfCommand())\n\t\tm.input.SetValue("")\n\t\tm.refreshViewportContent()\n\t\treturn nil\n\t}\n\tif strings.HasPrefix(strings.TrimSpace(value), "/ultracode") {\n\t\thandled, msg := m.handleUltracodeCommand(value)\n\t\tif handled {\n\t\t\tm.setEphemeralInfo(msg)\n\t\t\tm.input.SetValue("")\n\t\t\tm.refreshViewportContent()\n\t\t\treturn nil\n\t\t}\n\t}\n' + old_intercept

content = content.replace(old_intercept, new_intercept)

# 3. Add Self resolution in submitPromptTurn
content = content.replace(
    '\tm.clearEphemeralMessages()\n\tif m.assembler',
    '\tm.clearEphemeralMessages()\n\tif selfIntro, ok := blocks.ResolveSelfPrompt(value); ok {\n\t\tvalue = value + "\\n\\n[Identity: " + selfIntro + "]"\n\t}\n\tif m.assembler'
)

with open("/home/dev/whale/internal/tui/model_prompt.go", "w") as f:
    f.write(content)
print("patched")

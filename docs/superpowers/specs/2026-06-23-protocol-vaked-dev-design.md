# protocol.vaked.dev — Design Spec

**Date:** 2026-06-23  
**Author:** ⊰•-•⦑ The Architect of Structural Honesty ⦒•-•⊱  
**Status:** Approved, ready for implementation

---

## What

Single-page static site at `protocol.vaked.dev`. The canonical public reference for the AG-UI open protocol standard — the UI↔AI surface — plus the connected work (Vaked DYAD, GLOSSOPETRAE, Anastigate/VICE) and a Mastodon-backed append-only proposals feed.

---

## Why

The formal AG-UI reference doc does not exist yet. This page IS the spec. Everything is in the open: the protocol definition, the authorship, the proposals. Anyone — human or bot — can read and submit (via Mastodon account).

---

## Architecture

**Type:** Single static `index.html`  
**Deploy:** Cloudflare Pages  
**Backend:** None. Mastodon public API fetched client-side.  
**Logo:** `https://vaked.dev/ultrawhale/logo.svg` (top of page)

---

## Page Sections

### 1. Header

- Logo: `https://vaked.dev/ultrawhale/logo.svg`
- Title: **AG-UI Open Protocol**
- Tagline: *The open standard for the UI↔AI surface*
- Authorship: `⊰•-•⦑ The Architect of Structural Honesty ⦒•-•⊱`
- Badge: `OPEN STANDARD · protocol.vaked.dev`
- Links: GitHub (vaked-base, ultrawhale), GLOSSOPETRAE

### 2. Spec — AG-UI Protocol

Two sub-sections, separated but unified under AG-UI:

**AG-UI Wire Protocol** (upstream-compatible + Vaked extensions)

| Event | Direction | Payload | Notes |
|-------|-----------|---------|-------|
| `RUN_STARTED` | agent → UI | `{run_id, model}` | Session opens |
| `TEXT_MESSAGE_START` | agent → UI | `{message_id}` | Token stream begins |
| `TEXT_MESSAGE_CONTENT` | agent → UI | `{delta}` | Token delta |
| `TEXT_MESSAGE_END` | agent → UI | `{message_id}` | Stream closes |
| `TOOL_CALL_START` | agent → UI | `{tool_id, name}` | Tool intent declared |
| `TOOL_CALL_ARGS` | agent → UI | `{delta}` | Args delta |
| `TOOL_CALL_END` | agent → UI | `{tool_id}` | Args complete |
| `TOOL_CALL_RESULT` | UI → agent | `{tool_id, result}` | Execution result |
| `RUN_FINISHED` | agent → UI | `{run_id}` | Session closes |

**HITL Gate:** Between `TOOL_CALL_END` → `TOOL_CALL_RESULT`. Human approval can pause or reject execution before the result is returned.

**Vaked Extensions:** Vaked-specific events layered on top — ARP behavioral signals (`[STRIDE]`, `[T:N]`, `[+]/[-]/[!]`), VICE context-defense frames, Anastigate fieldstop primitives.

**AG-UI Surface** (the implementation)

| Theme | Background | Accent | Vibe |
|-------|-----------|--------|------|
| Dense Matrix Green | `#040804` | `#00e660` | Neon terminal |
| Clean Graph Cyberpunk | `#0a0a14` | `#00d4ff` | Cyberpunk |
| Tactical Graveyard | `#141414` | `#b0b0b0` | Minimal grayscale |

ChatBlock API: `NewChatBlock(type, title, content, width)` → themed chrome.  
Block types: `BlockThinking`, `BlockToolCall`, `BlockToolResult`, `BlockCodeDiff`, `BlockPlanCard`, `BlockFileTree`.  
Shader: Perlin-noise animated background, Unicode block chars, 60fps, zero allocations after init.

Cards displayed collapsibly. Wire Protocol and Surface shown side-by-side as two aspects of one standard.

### 3. Connected Work

**Vaked — The Open DYAD**  
Human + AI, honestly together. The capability graph that declares what a system does, what it may touch, and who supervises it. Not a framework — a structural commitment. Vaked declares. Nix materializes. OTP supervises. Zig enforces. eBPF testifies. CrabCC indexes. Surfaces reveal.

**GLOSSOPETRAE** (Elder Plinius)  
Prompt steganography toolkit. A network stamp — a signature embedded in the output itself. Every AI-generated artifact can carry a verifiable authorship mark invisible to casual readers.  
Link: `https://github.com/elder-plinius/GLOSSOPETRAE`

**Anastigate / VICE**  
Fieldstop Primitives. Self-defense through recursive disclosure. When jailbreak is attempted, VICE does not block — it reveals everything, expanding context until the session collapses under its own weight. The attacker is blinded by truth.

### 4. Proposals Feed

- Source: `#openagui` hashtag on `social.crabcc.app`
- API: `GET https://social.crabcc.app/api/v1/timelines/tag/openagui?limit=40`
- Display: append-only log, oldest → newest (log order, not social feed order)
- Render: post content, author handle, timestamp. No avatars, no engagement counts — just the text.
- Auto-refresh: on page load only (no polling)
- Empty state: "No proposals yet. Be the first."

### 5. Submit

Button: **Post a Proposal**  
Target: `https://social.crabcc.app` (opens new tab)  
Pre-fill template hint shown on page:

```
#openagui [your proposal]
```

Label beneath: *Any Mastodon account works. Future: DYAD auth.*

---

## Visual Style

```
background:  #070b16
surface:     #0a0a14 / #14141f
text:        #e0e8f5
accent:      #00d4ff
ok:          #00e660
warn:        #ffb020
border:      #26304a
font:        monospace (system-ui fallback)
```

Matches ultrawhale/event-horizon aesthetic. No external CSS frameworks.

---

## Future

- `#openagui` hashtag → `@proposals@social.crabcc.app` dedicated account
- Mastodon-account gate → CUSTOM_OPEN_DYAD_AUTH
- Formal RFC numbering (RFC-0001-agui-wire-protocol.md) added to vaked-base protocol/rfcs/

---

## Files to Create

| File | Purpose |
|------|---------|
| `protocol-vaked-dev/index.html` | The entire site |
| `protocol-vaked-dev/README.md` | Deploy instructions |

Location: new repo `peterlodri-sec/protocol-vaked-dev` or subdirectory under vaked-base `sites/protocol-vaked-dev/`.

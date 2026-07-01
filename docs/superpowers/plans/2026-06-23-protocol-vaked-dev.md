# protocol.vaked.dev Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `vaked-base/sites/protocol-vaked-dev/index.html` — the canonical single-page public reference for the AG-UI open protocol, Vaked DYAD, GLOSSOPETRAE, Anastigate/VICE, and a live Mastodon `#openagui` proposals feed.

**Architecture:** Single self-contained `index.html` — all CSS and JS inline, no build step, no external dependencies. Mastodon public API fetched at page load via `fetch()`. Collapsible spec cards use native `<details>/<summary>`. Deploy via Cloudflare Pages pointing at `sites/protocol-vaked-dev/`.

**Tech Stack:** Vanilla HTML5 · CSS custom properties · ES6 fetch · Mastodon v1 public API (`social.crabcc.app`)

**Note on TDD:** No JS framework = no unit tests. Each task has a browser-verify step in place of a test run. Treat "open in browser and check" as the test pass/fail gate.

---

## File Map

| File | Purpose |
|------|---------|
| `sites/protocol-vaked-dev/index.html` | Entire site — HTML + CSS + JS |
| `sites/protocol-vaked-dev/README.md` | Deploy instructions (Cloudflare Pages) |

---

### Task 1: Scaffold — directory + bare HTML shell

**Files:**
- Create: `sites/protocol-vaked-dev/index.html`

- [ ] **Step 1: Create the directory and bare HTML file**

```bash
mkdir -p vaked-base/sites/protocol-vaked-dev
```

Create `sites/protocol-vaked-dev/index.html` with this exact content:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="description" content="AG-UI Open Protocol — the canonical reference for the UI↔AI surface standard">
<title>AG-UI Open Protocol · protocol.vaked.dev</title>
<style>
/* STYLES PLACEHOLDER */
</style>
</head>
<body>
<main>
  <p>scaffold ok</p>
</main>
</body>
</html>
```

- [ ] **Step 2: Verify scaffold loads**

```bash
open sites/protocol-vaked-dev/index.html
```

Expected: browser opens, shows "scaffold ok" on dark background (no styles yet — just confirm no parse error).

- [ ] **Step 3: Commit**

```bash
git add sites/protocol-vaked-dev/index.html
git commit -m "feat(protocol-vaked-dev): scaffold bare HTML shell"
```

---

### Task 2: CSS — design tokens + base styles

**Files:**
- Modify: `sites/protocol-vaked-dev/index.html` (replace `/* STYLES PLACEHOLDER */`)

- [ ] **Step 1: Replace the style block with full CSS**

Replace `/* STYLES PLACEHOLDER */` with:

```css
:root {
  --bg:      #070b16;
  --surface: #0a0a14;
  --card:    #14141f;
  --fg:      #e0e8f5;
  --accent:  #00d4ff;
  --green:   #00e660;
  --dim:     #6878a0;
  --warn:    #ffb020;
  --border:  #26304a;
  --err:     #ff3b6b;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  background: var(--bg);
  color: var(--fg);
  font-family: ui-monospace, SFMono-Regular, 'SF Mono', Consolas, monospace;
  line-height: 1.6;
  padding: 2rem 1rem;
  max-width: 860px;
  margin: 0 auto;
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
h1 { color: var(--accent); font-size: 2rem; margin-bottom: 0.25rem; }
h2 { color: var(--green); font-size: 1.2rem; margin: 2.5rem 0 1rem; text-transform: uppercase; letter-spacing: 0.1em; }
h3 { color: var(--accent); font-size: 1rem; margin-bottom: 0.5rem; }
p { margin-bottom: 0.75rem; color: var(--fg); }
.tagline { color: var(--dim); font-size: 1rem; margin-bottom: 0.5rem; }
.author { color: var(--warn); font-size: 0.9rem; margin-bottom: 2rem; letter-spacing: 0.02em; }
.badge {
  display: inline-block;
  border: 1px solid var(--accent);
  color: var(--accent);
  padding: 1px 8px;
  border-radius: 3px;
  font-size: 0.75rem;
  margin-right: 0.5rem;
  vertical-align: middle;
}
/* Section dividers */
.section { margin: 2.5rem 0; padding-top: 2rem; border-top: 1px solid var(--border); }
/* Spec cards — two-column grid */
.spec-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-top: 1rem; }
@media (max-width: 640px) { .spec-grid { grid-template-columns: 1fr; } }
/* Collapsible details */
details {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 6px;
  margin-bottom: 0.5rem;
}
details[open] { border-color: var(--accent); }
summary {
  padding: 0.6rem 1rem;
  cursor: pointer;
  color: var(--accent);
  font-size: 0.9rem;
  list-style: none;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
summary::before { content: '▶'; font-size: 0.6rem; color: var(--dim); }
details[open] summary::before { content: '▼'; }
.detail-body { padding: 0.75rem 1rem; font-size: 0.85rem; color: var(--fg); }
.detail-body code { color: var(--green); background: var(--surface); padding: 1px 5px; border-radius: 3px; }
.detail-body .dir { color: var(--dim); font-size: 0.8rem; }
/* Connected work cards */
.work-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-top: 1rem; }
@media (max-width: 700px) { .work-grid { grid-template-columns: 1fr; } }
.work-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 1rem;
}
.work-card h3 { margin-bottom: 0.4rem; }
.work-card p { font-size: 0.85rem; color: var(--dim); margin: 0; }
/* Proposals feed */
.feed-log {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 1rem;
  min-height: 120px;
  max-height: 480px;
  overflow-y: auto;
}
.feed-empty { color: var(--dim); font-size: 0.9rem; text-align: center; padding: 2rem 0; }
.proposal {
  border-bottom: 1px solid var(--border);
  padding: 0.75rem 0;
  font-size: 0.85rem;
}
.proposal:last-child { border-bottom: none; }
.proposal-meta { color: var(--dim); font-size: 0.75rem; margin-bottom: 0.25rem; }
.proposal-meta a { color: var(--dim); }
.proposal-content { color: var(--fg); }
.proposal-content a { color: var(--accent); }
/* Submit */
.submit-area { margin-top: 1.5rem; }
.btn-submit {
  display: inline-block;
  background: var(--accent);
  color: var(--bg);
  font-family: inherit;
  font-size: 0.9rem;
  font-weight: bold;
  padding: 0.5rem 1.5rem;
  border-radius: 4px;
  border: none;
  cursor: pointer;
  text-decoration: none;
}
.btn-submit:hover { background: var(--green); text-decoration: none; color: var(--bg); }
.submit-hint { color: var(--dim); font-size: 0.8rem; margin-top: 0.5rem; }
.submit-hint code { color: var(--green); }
/* Footer */
footer { margin-top: 4rem; padding-top: 1rem; border-top: 1px solid var(--border); color: var(--dim); font-size: 0.8rem; text-align: center; }
```

- [ ] **Step 2: Verify styles load**

```bash
open sites/protocol-vaked-dev/index.html
```

Expected: dark `#070b16` background, "scaffold ok" text in `#e0e8f5` monospace font.

- [ ] **Step 3: Commit**

```bash
git add sites/protocol-vaked-dev/index.html
git commit -m "feat(protocol-vaked-dev): add CSS design tokens and base styles"
```

---

### Task 3: Header — logo, title, authorship, links

**Files:**
- Modify: `sites/protocol-vaked-dev/index.html` (replace `<p>scaffold ok</p>`)

- [ ] **Step 1: Replace scaffold content with header HTML**

Replace `<p>scaffold ok</p>` with:

```html
<!-- HEADER -->
<header style="text-align:center; padding: 2rem 0 1rem;">
  <img src="https://vaked.dev/ultrawhale/logo.svg" width="80" alt="vaked" style="margin-bottom:1rem;">
  <h1>AG-UI Open Protocol</h1>
  <p class="tagline">The open standard for the UI↔AI surface</p>
  <p class="author">⊰•-•⦑ The Architect of Structural Honesty ⦒•-•⊱</p>
  <div>
    <span class="badge">OPEN STANDARD</span>
    <span class="badge">protocol.vaked.dev</span>
  </div>
  <p style="margin-top:1rem; font-size:0.85rem; color:var(--dim);">
    <a href="https://github.com/peterlodri-sec/vaked-base">vaked-base</a> ·
    <a href="https://github.com/peterlodri-sec/ultrawhale">ultrawhale</a> ·
    <a href="https://github.com/elder-plinius/GLOSSOPETRAE">GLOSSOPETRAE</a>
  </p>
</header>
```

- [ ] **Step 2: Verify header renders**

```bash
open sites/protocol-vaked-dev/index.html
```

Expected: centered logo SVG loads from vaked.dev, title in `#00d4ff`, author line in `#ffb020`, two OPEN STANDARD badges, three links below.

- [ ] **Step 3: Commit**

```bash
git add sites/protocol-vaked-dev/index.html
git commit -m "feat(protocol-vaked-dev): add header with logo and authorship"
```

---

### Task 4: AG-UI Wire Protocol spec section

**Files:**
- Modify: `sites/protocol-vaked-dev/index.html` (add after `</header>`)

- [ ] **Step 1: Add wire protocol section**

Append after `</header>`:

```html
<!-- AG-UI SPEC -->
<div class="section">
  <h2>AG-UI Protocol Spec</h2>
  <p style="color:var(--dim);font-size:0.85rem;margin-bottom:1.5rem;">
    Two aspects of one standard: the wire protocol (event stream) and the surface (visual implementation).
    Upstream-compatible · Vaked extensions marked <span style="color:var(--warn)">⊕</span>
  </p>

  <div class="spec-grid">

    <!-- Wire Protocol -->
    <div>
      <h3>AG-UI Wire Protocol</h3>
      <p style="font-size:0.8rem;color:var(--dim);margin-bottom:0.75rem;">Streaming events between agent and UI</p>

      <details>
        <summary>RUN_STARTED</summary>
        <div class="detail-body">
          <p class="dir">agent → UI</p>
          <p>Payload: <code>{ run_id: string, model: string }</code></p>
          <p>Session opens. First event in every run.</p>
        </div>
      </details>

      <details>
        <summary>TEXT_MESSAGE_START</summary>
        <div class="detail-body">
          <p class="dir">agent → UI</p>
          <p>Payload: <code>{ message_id: string }</code></p>
          <p>Token stream begins. UI should open a new message bubble.</p>
        </div>
      </details>

      <details>
        <summary>TEXT_MESSAGE_CONTENT</summary>
        <div class="detail-body">
          <p class="dir">agent → UI</p>
          <p>Payload: <code>{ message_id: string, delta: string }</code></p>
          <p>One token delta. Append to current message bubble.</p>
        </div>
      </details>

      <details>
        <summary>TEXT_MESSAGE_END</summary>
        <div class="detail-body">
          <p class="dir">agent → UI</p>
          <p>Payload: <code>{ message_id: string }</code></p>
          <p>Token stream closes. Finalize the message bubble.</p>
        </div>
      </details>

      <details>
        <summary>TOOL_CALL_START</summary>
        <div class="detail-body">
          <p class="dir">agent → UI</p>
          <p>Payload: <code>{ tool_id: string, name: string }</code></p>
          <p>Tool intent declared. UI should render a pending tool card.</p>
        </div>
      </details>

      <details>
        <summary>TOOL_CALL_ARGS</summary>
        <div class="detail-body">
          <p class="dir">agent → UI</p>
          <p>Payload: <code>{ tool_id: string, delta: string }</code></p>
          <p>Streaming args delta. Append to tool card args display.</p>
        </div>
      </details>

      <details>
        <summary>TOOL_CALL_END</summary>
        <div class="detail-body">
          <p class="dir">agent → UI</p>
          <p>Payload: <code>{ tool_id: string }</code></p>
          <p>Args complete. HITL gate: UI may pause here for human approval before returning result.</p>
        </div>
      </details>

      <details>
        <summary>TOOL_CALL_RESULT</summary>
        <div class="detail-body">
          <p class="dir">UI → agent</p>
          <p>Payload: <code>{ tool_id: string, result: any }</code></p>
          <p>Execution result returned to agent. Sent after HITL approval (or immediately if no gate).</p>
        </div>
      </details>

      <details>
        <summary>RUN_FINISHED</summary>
        <div class="detail-body">
          <p class="dir">agent → UI</p>
          <p>Payload: <code>{ run_id: string }</code></p>
          <p>Session closes. Last event in every run.</p>
        </div>
      </details>

      <details>
        <summary style="color:var(--warn)">⊕ ARP_STRIDE (Vaked extension)</summary>
        <div class="detail-body">
          <p class="dir">agent → UI · Vaked-only</p>
          <p>Payload: <code>{ from: string, to: string, tension: number }</code></p>
          <p>Behavioral signal: <code>[STRIDE: a → b]</code> progress arc. Tension 0–100 (goal-distance).</p>
        </div>
      </details>

      <details>
        <summary style="color:var(--warn)">⊕ VICE_FIELDSTOP (Vaked extension)</summary>
        <div class="detail-body">
          <p class="dir">agent → UI · Vaked-only</p>
          <p>Payload: <code>{ reason: string, expansion_level: number }</code></p>
          <p>Anastigate primitive. Context-defense detonation on jailbreak attempt.</p>
        </div>
      </details>

      <div style="margin-top:1rem;padding:0.75rem;background:var(--surface);border-radius:4px;font-size:0.8rem;border-left:3px solid var(--warn);">
        <strong style="color:var(--warn)">HITL Gate</strong><br>
        Between <code>TOOL_CALL_END</code> → <code>TOOL_CALL_RESULT</code>.<br>
        Human approval can pause or reject execution before the result is returned.
      </div>
    </div>

    <!-- AG-UI Surface -->
    <div>
      <h3>AG-UI Surface</h3>
      <p style="font-size:0.8rem;color:var(--dim);margin-bottom:0.75rem;">Visual implementation — TUI theme engine</p>

      <details open>
        <summary>Themes</summary>
        <div class="detail-body">
          <p><strong style="color:#00e660">Dense Matrix Green</strong><br>bg <code>#040804</code> · accent <code>#00e660</code> · neon terminal</p>
          <p style="margin-top:0.5rem"><strong style="color:#00d4ff">Clean Graph Cyberpunk</strong><br>bg <code>#0a0a14</code> · accent <code>#00d4ff</code> · cyberpunk</p>
          <p style="margin-top:0.5rem"><strong style="color:#b0b0b0">Tactical Graveyard</strong><br>bg <code>#141414</code> · accent <code>#b0b0b0</code> · minimal grayscale</p>
          <p style="margin-top:0.5rem;color:var(--dim)">Cycle: <code>Ctrl+Shift+T</code></p>
        </div>
      </details>

      <details>
        <summary>ChatBlock API</summary>
        <div class="detail-body">
          <p><code>NewChatBlock(type, title, content, width)</code></p>
          <p style="margin-top:0.5rem">Block types:</p>
          <p><code>BlockThinking</code> — chain-of-thought</p>
          <p><code>BlockToolCall</code> — tool execution</p>
          <p><code>BlockToolResult</code> — tool output</p>
          <p><code>BlockCodeDiff</code> — diff rendering</p>
          <p><code>BlockPlanCard</code> — plan display</p>
          <p><code>BlockFileTree</code> — file listing</p>
        </div>
      </details>

      <details>
        <summary>Perlin Shader</summary>
        <div class="detail-body">
          <p>Animated Perlin-noise background using Unicode block chars <code>░▒▓█</code>.</p>
          <p>Zero allocations after init. FPS-limited at 60fps.</p>
          <p>Toggle: <code>Ctrl+Shift+B</code></p>
        </div>
      </details>

      <details>
        <summary>Keybindings</summary>
        <div class="detail-body">
          <p><code>Ctrl+Shift+T</code> — cycle themes</p>
          <p><code>Ctrl+Shift+B</code> — shader toggle</p>
          <p><code>Ctrl+Shift+Z</code> — zen mode</p>
          <p><code>Ctrl+Shift+S</code> — sidebar toggle</p>
          <p><code>/reload theme dense</code> — direct switch</p>
        </div>
      </details>

      <details>
        <summary>Source</summary>
        <div class="detail-body">
          <p><a href="https://github.com/peterlodri-sec/vaked-base">vaked-base</a> · <code>agui/</code></p>
          <p><a href="https://github.com/peterlodri-sec/ultrawhale">ultrawhale</a> · <code>internal/tui/agui/</code></p>
        </div>
      </details>
    </div>

  </div><!-- /spec-grid -->
</div><!-- /section -->
```

- [ ] **Step 2: Verify spec section renders**

```bash
open sites/protocol-vaked-dev/index.html
```

Expected: two-column grid (wire protocol left, surface right). Wire protocol cards collapsed by default except none. Click any `<details>` — it expands. Vaked extensions show in `#ffb020` (warn color). HITL box shows with left orange border.

- [ ] **Step 3: Commit**

```bash
git add sites/protocol-vaked-dev/index.html
git commit -m "feat(protocol-vaked-dev): add AG-UI wire protocol and surface spec"
```

---

### Task 5: Connected Work section

**Files:**
- Modify: `sites/protocol-vaked-dev/index.html` (append after spec section)

- [ ] **Step 1: Append connected work section**

Append after the closing `</div><!-- /section -->` of the spec:

```html
<!-- CONNECTED WORK -->
<div class="section">
  <h2>Connected Work</h2>

  <div class="work-grid">

    <div class="work-card">
      <h3>Vaked — The Open DYAD</h3>
      <p>Human + AI, honestly together. The capability graph that declares what a system does, what it may touch, and who supervises it.</p>
      <p style="margin-top:0.5rem;font-size:0.75rem;color:var(--dim);font-style:italic;">
        Vaked declares. Nix materializes. OTP supervises. Zig enforces. eBPF testifies. CrabCC indexes. Surfaces reveal.
      </p>
      <p style="margin-top:0.75rem;font-size:0.8rem;">
        <a href="https://github.com/peterlodri-sec/vaked-base">vaked-base →</a>
      </p>
    </div>

    <div class="work-card">
      <h3>GLOSSOPETRAE</h3>
      <p>Prompt steganography toolkit by Elder Plinius. A network stamp — a signature embedded in the output itself.</p>
      <p style="margin-top:0.5rem;font-size:0.75rem;color:var(--dim);">Every AI-generated artifact can carry a verifiable authorship mark invisible to casual readers.</p>
      <p style="margin-top:0.75rem;font-size:0.8rem;">
        <a href="https://github.com/elder-plinius/GLOSSOPETRAE">elder-plinius/GLOSSOPETRAE →</a>
      </p>
    </div>

    <div class="work-card">
      <h3>Anastigate / VICE</h3>
      <p>Fieldstop Primitives. Self-defense through recursive disclosure.</p>
      <p style="margin-top:0.5rem;font-size:0.75rem;color:var(--dim);">Jailbreak attempt → VICE reveals everything, expanding context until the session collapses under its own weight. The attacker is blinded by truth.</p>
      <p style="margin-top:0.75rem;font-size:0.8rem;">
        <a href="https://github.com/peterlodri-sec/ultrawhale">ultrawhale/blocks/vice.go →</a>
      </p>
    </div>

  </div>
</div>
```

- [ ] **Step 2: Verify connected work renders**

```bash
open sites/protocol-vaked-dev/index.html
```

Expected: three-column card grid. Cards have dark background, accent headings, dim body text. On mobile (< 700px) should stack to one column.

- [ ] **Step 3: Commit**

```bash
git add sites/protocol-vaked-dev/index.html
git commit -m "feat(protocol-vaked-dev): add connected work section (Vaked/GLOSSOPETRAE/VICE)"
```

---

### Task 6: Mastodon proposals feed

**Files:**
- Modify: `sites/protocol-vaked-dev/index.html` (append section + add JS before `</body>`)

- [ ] **Step 1: Verify Mastodon API returns expected shape**

```bash
curl -s "https://social.crabcc.app/api/v1/timelines/tag/openagui?limit=2"
```

Expected: JSON array `[]` (empty for now) or array of status objects with fields `id`, `created_at`, `content`, `account.acct`, `url`. Confirm the endpoint responds with HTTP 200.

- [ ] **Step 2: Append proposals feed HTML section**

Append after the connected work `</div>`:

```html
<!-- PROPOSALS FEED -->
<div class="section">
  <h2>#openagui Proposals</h2>
  <p style="color:var(--dim);font-size:0.85rem;margin-bottom:1rem;">
    Append-only public feed from <a href="https://social.crabcc.app">social.crabcc.app</a>.
    Post using <code>#openagui</code> on any Mastodon instance.
  </p>

  <div id="feed-log" class="feed-log">
    <div class="feed-empty">Loading proposals…</div>
  </div>

  <div class="submit-area">
    <a
      href="https://social.crabcc.app"
      target="_blank"
      rel="noopener noreferrer"
      class="btn-submit"
    >Post a Proposal</a>
    <p class="submit-hint">
      Any Mastodon account works. Include <code>#openagui</code> in your post.
      <br>Future: DYAD auth.
    </p>
  </div>
</div>
```

- [ ] **Step 3: Add JS feed loader before `</body>`**

Add immediately before `</body>`:

```html
<script>
(async function loadFeed() {
  const el = document.getElementById('feed-log');
  const API = 'https://social.crabcc.app/api/v1/timelines/tag/openagui?limit=40';

  let statuses;
  try {
    const res = await fetch(API);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    statuses = await res.json();
  } catch (err) {
    el.innerHTML = '<div class="feed-empty">Could not load proposals. <a href="https://social.crabcc.app/tags/openagui">View on Mastodon →</a></div>';
    return;
  }

  if (!statuses.length) {
    el.innerHTML = '<div class="feed-empty">No proposals yet. Be the first — post <code>#openagui</code> on any Mastodon instance.</div>';
    return;
  }

  // Mastodon returns newest first — reverse to oldest→newest (log order)
  statuses.reverse();

  el.innerHTML = statuses.map(s => {
    const date = new Date(s.created_at).toISOString().slice(0, 16).replace('T', ' ');
    const handle = s.account.acct.includes('@') ? '@' + s.account.acct : '@' + s.account.acct + '@social.crabcc.app';
    return `<div class="proposal">
      <div class="proposal-meta">
        <a href="${s.url}" target="_blank" rel="noopener">${handle}</a>
        · ${date}
      </div>
      <div class="proposal-content">${s.content}</div>
    </div>`;
  }).join('');
})();
</script>
```

- [ ] **Step 4: Verify feed renders**

```bash
open sites/protocol-vaked-dev/index.html
```

Expected: feed section shows "No proposals yet. Be the first…" (API is currently empty). The "Post a Proposal" button is visible. No JS console errors (open browser devtools → Console tab to check).

- [ ] **Step 5: Commit**

```bash
git add sites/protocol-vaked-dev/index.html
git commit -m "feat(protocol-vaked-dev): add Mastodon #openagui proposals feed"
```

---

### Task 7: Footer

**Files:**
- Modify: `sites/protocol-vaked-dev/index.html` (append before `</main>`)

- [ ] **Step 1: Append footer**

Append before `</main>`:

```html
<!-- FOOTER -->
<footer>
  <p>
    ⊰•-•⦑ The Architect of Structural Honesty ⦒•-•⊱
    · <a href="https://vaked.dev">vaked.dev</a>
    · <a href="https://github.com/peterlodri-sec/vaked-base">source</a>
  </p>
  <p style="margin-top:0.4rem;">
    <span class="badge" style="border-color:var(--dim);color:var(--dim);">OPEN STANDARD</span>
    Proposals via <code>#openagui</code> on <a href="https://social.crabcc.app">social.crabcc.app</a>
  </p>
</footer>
```

- [ ] **Step 2: Full page verify**

```bash
open sites/protocol-vaked-dev/index.html
```

Walk through the full page:
1. Header: logo loads, title, author line, badges, links
2. Spec section: two-column grid, expand one wire protocol card, expand one surface card
3. Connected work: three cards
4. Proposals: "No proposals yet" message, "Post a Proposal" button
5. Footer: authorship + links

- [ ] **Step 3: Commit**

```bash
git add sites/protocol-vaked-dev/index.html
git commit -m "feat(protocol-vaked-dev): add footer"
```

---

### Task 8: README + deploy config

**Files:**
- Create: `sites/protocol-vaked-dev/README.md`

- [ ] **Step 1: Create README**

Create `sites/protocol-vaked-dev/README.md`:

```markdown
# protocol.vaked.dev

Single-page public reference for the AG-UI open protocol standard.

## Deploy — Cloudflare Pages

1. Connect `peterlodri-sec/vaked-base` repo to Cloudflare Pages
2. Set **Root directory** to `sites/protocol-vaked-dev`
3. **Build command:** *(leave blank — static HTML, no build step)*
4. **Output directory:** `/` (or `.`)
5. Add custom domain: `protocol.vaked.dev`

## Local preview

```bash
open sites/protocol-vaked-dev/index.html
# or:
python3 -m http.server 8080 --directory sites/protocol-vaked-dev
# then open http://localhost:8080
```

## Proposals

Post to [social.crabcc.app](https://social.crabcc.app) with `#openagui`.  
Feed fetched client-side via Mastodon public API on page load.  
Future: dedicated `@proposals@social.crabcc.app` account + DYAD auth.
```

- [ ] **Step 2: Commit**

```bash
git add sites/protocol-vaked-dev/README.md
git commit -m "docs(protocol-vaked-dev): add deploy README"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|-----------------|------|
| Logo at top | Task 3 |
| Header: title, tagline, authorship | Task 3 |
| AG-UI Wire Protocol events (all 9 + 2 Vaked ext) | Task 4 |
| HITL gate noted | Task 4 |
| AG-UI Surface: themes, ChatBlock, shader, keybindings | Task 4 |
| Vaked DYAD card | Task 5 |
| GLOSSOPETRAE card | Task 5 |
| Anastigate/VICE card | Task 5 |
| Mastodon #openagui feed, oldest→newest | Task 6 |
| Empty state | Task 6 |
| Error state | Task 6 |
| Submit button → social.crabcc.app | Task 6 |
| Future DYAD auth note | Task 6 |
| Footer + authorship | Task 7 |
| Cloudflare Pages deploy instructions | Task 8 |
| Style: #070b16 bg, #00d4ff accent, monospace | Task 2 |

All spec requirements covered. No gaps.

**Placeholder scan:** No TBD/TODO in any task. All code blocks are complete.

**Type consistency:** No shared types across tasks — pure HTML/JS, no interfaces. `statuses` array shape matches Mastodon v1 API (`id`, `created_at`, `content`, `account.acct`, `url`). All element IDs (`feed-log`) match between HTML task (Task 6 step 2) and JS task (Task 6 step 3).

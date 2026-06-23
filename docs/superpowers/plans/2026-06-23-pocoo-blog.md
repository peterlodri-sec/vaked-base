# pocoo.vaked.dev Blog — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and deploy a personal technical blog at `pocoo.vaked.dev` — static HTML, Atom RSS, protocol.vaked.dev aesthetic, Tier 2 telemetry.

**Architecture:** Fork `crabcc.app-blog`'s `build.mjs` pipeline (markdown-it, frontmatter, draft filter). Drop the `_ds` crabcc design system entirely; replace with a single self-contained `blog.css` using protocol.vaked.dev CSS vars. Add Atom feed generation and inline telemetry script injection to the build. Deploy on Cloudflare Pages.

**Tech Stack:** Node.js (ESM), markdown-it ^14, Cloudflare Pages, chat.vaked.dev telemetry API.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `pocoo.vaked.dev/package.json` | Create | Node project, single dep markdown-it |
| `pocoo.vaked.dev/.gitignore` | Create | Ignore dist/, node_modules/ |
| `pocoo.vaked.dev/assets/blog.css` | Create | Protocol.vaked.dev aesthetic, all styles |
| `pocoo.vaked.dev/build.mjs` | Create | Build script — renders posts, index, feed.xml |
| `pocoo.vaked.dev/_headers` | Create | Cloudflare Pages headers + feed.xml content-type |
| `pocoo.vaked.dev/posts/.keep` | Create | Empty placeholder so posts/ is committed |
| `ultrawhale/site/hf-dataset-card.md` | Modify | Add pocoo.vaked.dev row to site table |
| `ultrawhale/.github/workflows/hf-publish.yml` | Modify | Add pocoo.vaked.dev to telemetry sources + links |

---

## Task 1: Scaffold repo

**Files:**
- Create: `pocoo.vaked.dev/package.json`
- Create: `pocoo.vaked.dev/.gitignore`
- Create: `pocoo.vaked.dev/posts/.keep`

- [ ] **Step 1: Create directory and init git**

```bash
mkdir -p /Users/lodripeter/workspace/peterlodri-sec/pocoo.vaked.dev/posts
mkdir -p /Users/lodripeter/workspace/peterlodri-sec/pocoo.vaked.dev/assets
cd /Users/lodripeter/workspace/peterlodri-sec/pocoo.vaked.dev
git init
```

- [ ] **Step 2: Write package.json**

Create `/Users/lodripeter/workspace/peterlodri-sec/pocoo.vaked.dev/package.json`:

```json
{
  "name": "pocoo-vaked-dev",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "description": "Personal blog at pocoo.vaked.dev",
  "scripts": {
    "build": "node build.mjs"
  },
  "dependencies": {
    "markdown-it": "^14.1.0"
  }
}
```

- [ ] **Step 3: Write .gitignore**

Create `/Users/lodripeter/workspace/peterlodri-sec/pocoo.vaked.dev/.gitignore`:

```
dist/
node_modules/
```

- [ ] **Step 4: Create posts placeholder**

Create `/Users/lodripeter/workspace/peterlodri-sec/pocoo.vaked.dev/posts/.keep` (empty file).

- [ ] **Step 5: Install dep**

```bash
cd /Users/lodripeter/workspace/peterlodri-sec/pocoo.vaked.dev
npm install
```

Expected: `node_modules/` created, `package-lock.json` generated.

- [ ] **Step 6: Commit scaffold**

```bash
git add package.json package-lock.json .gitignore posts/.keep
git commit -m "chore: scaffold pocoo.vaked.dev"
```

---

## Task 2: Write blog.css

**Files:**
- Create: `pocoo.vaked.dev/assets/blog.css`

- [ ] **Step 1: Write the full CSS file**

Create `/Users/lodripeter/workspace/peterlodri-sec/pocoo.vaked.dev/assets/blog.css`:

```css
/* pocoo.vaked.dev — protocol.vaked.dev aesthetic */
:root {
  --bg:      #070b16;
  --surface: #0a0a14;
  --card:    #14141f;
  --fg:      #e0e8f5;
  --accent:  #00d4ff;
  --green:   #00e660;
  --dim:     #6878a0;
  --border:  #26304a;
  --warn:    #ffb020;
}

*, *::before, *::after { box-sizing: border-box; }

html { color-scheme: dark; }

body {
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  font-family: ui-monospace, SFMono-Regular, 'SF Mono', Consolas, monospace;
  font-size: 15px;
  line-height: 1.7;
  padding: 2rem 1rem;
}

a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }

/* ── Index ──────────────────────────────────────────────────── */
.index {
  max-width: 860px;
  margin: 0 auto;
}

.index-head {
  margin-bottom: 3rem;
  padding-bottom: 2rem;
  border-bottom: 1px solid var(--border);
}

.index-head h1 {
  margin: 0 0 0.5rem;
  font-size: 2rem;
  color: var(--accent);
  letter-spacing: 0.04em;
}

.lede {
  color: var(--dim);
  font-size: 0.9rem;
  margin: 0;
}

.post-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.entry {
  padding: 1.5rem 0;
  border-bottom: 1px solid var(--border);
}

.entry:last-child { border-bottom: none; }

.entry-title {
  margin: 0 0 0.25rem;
  font-size: 1.1rem;
  font-weight: 600;
}

.entry-title a {
  color: var(--fg);
}

.entry-title a:hover {
  color: var(--accent);
  text-decoration: none;
}

.entry-desc {
  margin: 0.25rem 0 0;
  color: var(--dim);
  font-size: 0.85rem;
}

/* ── Post ───────────────────────────────────────────────────── */
.post {
  max-width: 860px;
  margin: 0 auto;
}

.back {
  margin: 0 0 2rem;
  font-size: 0.85rem;
}

.back a { color: var(--dim); }
.back a:hover { color: var(--accent); }

.post-head {
  margin-bottom: 2.5rem;
  padding-bottom: 1.5rem;
  border-bottom: 1px solid var(--border);
}

.post-head h1 {
  margin: 0 0 0.5rem;
  font-size: 1.75rem;
  color: var(--accent);
  line-height: 1.3;
}

/* ── Shared meta + tags ─────────────────────────────────────── */
.meta {
  margin: 0;
  color: var(--dim);
  font-size: 0.8rem;
}

.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  list-style: none;
  margin: 0.75rem 0 0;
  padding: 0;
}

.tag {
  display: inline-block;
  border: 1px solid var(--border);
  color: var(--warn);
  padding: 1px 7px;
  border-radius: 3px;
  font-size: 0.72rem;
  letter-spacing: 0.04em;
}

/* ── Prose (post body) ──────────────────────────────────────── */
.prose { line-height: 1.75; }

.prose h2 {
  color: var(--green);
  font-size: 1.05rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  margin: 2.5rem 0 1rem;
  padding-top: 2rem;
  border-top: 1px solid var(--border);
}

.prose h3 {
  color: var(--accent);
  font-size: 0.95rem;
  margin: 1.5rem 0 0.5rem;
}

.prose p { margin: 0 0 1rem; }

.prose ul, .prose ol {
  margin: 0 0 1rem 1.5rem;
  padding: 0;
}

.prose li { margin-bottom: 0.25rem; }

.prose blockquote {
  margin: 1.5rem 0;
  padding: 0.75rem 1rem;
  border-left: 3px solid var(--accent);
  background: var(--surface);
  color: var(--dim);
}

.prose blockquote p { margin: 0; }

.prose code {
  font-family: inherit;
  background: var(--card);
  color: var(--green);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 0.9em;
}

.prose pre {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 1rem;
  overflow-x: auto;
  margin: 1.25rem 0;
}

.prose pre code {
  background: none;
  padding: 0;
  border-radius: 0;
  font-size: 0.85em;
  color: var(--fg);
}

.prose table {
  border-collapse: collapse;
  width: 100%;
  margin: 1.25rem 0;
  font-size: 0.875rem;
}

.prose th, .prose td {
  border: 1px solid var(--border);
  padding: 0.5rem 0.75rem;
  text-align: left;
}

.prose th {
  background: var(--surface);
  color: var(--green);
  font-weight: 600;
}

.prose hr {
  border: none;
  border-top: 1px solid var(--border);
  margin: 2rem 0;
}

.prose a { color: var(--accent); }
.prose a:hover { text-decoration: underline; }
```

- [ ] **Step 2: Commit**

```bash
cd /Users/lodripeter/workspace/peterlodri-sec/pocoo.vaked.dev
git add assets/blog.css
git commit -m "feat: blog.css — protocol.vaked.dev aesthetic"
```

---

## Task 3: Write build.mjs

**Files:**
- Create: `pocoo.vaked.dev/build.mjs`

This is the core build script. Forked from `crabcc.app-blog/build.mjs` with: `_ds` removed, branding updated, RSS added, telemetry injected.

- [ ] **Step 1: Write build.mjs**

Create `/Users/lodripeter/workspace/peterlodri-sec/pocoo.vaked.dev/build.mjs`:

```javascript
// pocoo.vaked.dev — static blog builder
// Forked from crabcc.app-blog/build.mjs; dropped _ds, added RSS + telemetry.
// Run: node build.mjs

import { readdir, readFile, mkdir, writeFile, cp, rm } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import MarkdownIt from "markdown-it";

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const POSTS_DIR = path.join(ROOT, "posts");
const DIST_DIR = path.join(ROOT, "dist");

const md = new MarkdownIt({
  html: false,
  linkify: false,
  typographer: false,
}).enable(["table", "fence", "code"]);

function esc(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function parseFrontmatter(raw) {
  const text = raw.replace(/^﻿/, "");
  if (!text.startsWith("---")) return { meta: {}, body: text };
  const lines = text.split(/\r?\n/);
  let end = -1;
  for (let i = 1; i < lines.length; i++) {
    if (lines[i].trim() === "---") { end = i; break; }
  }
  if (end === -1) return { meta: {}, body: text };
  const block = lines.slice(1, end);
  const body = lines.slice(end + 1).join("\n");
  const meta = {};
  for (const line of block) {
    if (!line.trim() || /^\s*#/.test(line)) continue;
    const m = line.match(/^([A-Za-z0-9_-]+):\s*(.*)$/);
    if (!m) continue;
    const key = m[1].trim();
    let val = m[2].trim();
    if (key === "tags") meta.tags = parseList(val);
    else if (key === "draft") meta.draft = /^true$/i.test(val);
    else meta[key] = stripQuotes(val);
  }
  return { meta, body };
}

function stripQuotes(v) {
  if ((v.startsWith('"') && v.endsWith('"')) ||
      (v.startsWith("'") && v.endsWith("'"))) return v.slice(1, -1);
  return v;
}

function parseList(v) {
  let s = v.trim();
  if (s.startsWith("[") && s.endsWith("]")) s = s.slice(1, -1);
  if (!s.trim()) return [];
  return s.split(",").map((x) => stripQuotes(x.trim())).filter(Boolean);
}

function slugOf(filename) {
  return filename.replace(/\.md$/i, "");
}

function displayDate(date) {
  const m = String(date || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return esc(String(date || ""));
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return `${months[Number(m[2]) - 1]} ${Number(m[3])}, ${m[1]}`;
}

function tagsHtml(tags) {
  if (!tags || !tags.length) return "";
  return `<ul class="tags">${tags.map((t) => `<li class="tag">${esc(t)}</li>`).join("")}</ul>`;
}

// ── Telemetry (Tier 2 — no PII) ─────────────────────────────────────────────
// Same pattern as music.vaked.dev, irc.vaked.dev.
// Events: page_view, post_read (45s threshold, post pages only), session_end.
function telemetryScript(isPost, slug, title) {
  const slugLit = esc(slug || "index");
  const titleLit = title ? esc(title) : "";
  const readTimer = isPost
    ? `var _rf=false;setTimeout(function(){if(!_rf){_rf=true;record('post_read',{slug:'${slugLit}',read_duration_sec:45});}},45000);`
    : "";
  const slugField = isPost
    ? `slug:'${slugLit}',title:'${titleLit}'`
    : `slug:'index'`;
  return `<script>
(function(){
  var E='https://chat.vaked.dev/api/telemetry';
  var sid=crypto.randomUUID?crypto.randomUUID():(Date.now().toString(36)+'-'+Math.random().toString(36).slice(2));
  var t0=Date.now(),buf=[];
  function flush(){if(!buf.length)return;var ev=buf.splice(0);fetch(E,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({events:ev})}).catch(function(){});}
  function record(type,data){buf.push(Object.assign({type:type,timestamp:Date.now(),session_id:sid,page:'pocoo.vaked.dev'},data||{}));flush();}
  record('page_view',{${slugField}});
  ${readTimer}
  window.addEventListener('beforeunload',function(){
    record('session_end',{duration_sec:Math.round((Date.now()-t0)/1000)${isPost ? `,slug:'${slugLit}'` : ""}});
    if(buf.length)navigator.sendBeacon(E,JSON.stringify({events:buf}));
  });
})();
<\/script>`;
}

// ── <head> ────────────────────────────────────────────────────────────────────
function head({ title, description, prefix, ogType }) {
  const desc = esc(description || "");
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title)}</title>
<meta name="description" content="${desc}">
<meta property="og:type" content="${ogType}">
<meta property="og:title" content="${esc(title)}">
<meta property="og:description" content="${desc}">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="${esc(title)}">
<meta name="twitter:description" content="${desc}">
<meta name="theme-color" content="#070b16">
<link rel="alternate" type="application/atom+xml" title="pocoo" href="${prefix}feed.xml">
<link rel="stylesheet" href="${prefix}assets/blog.css">
</head>`;
}

// ── Post page ─────────────────────────────────────────────────────────────────
function renderPost(post) {
  const bodyHtml = md.render(post.body);
  return `${head({
    title: `${post.meta.title} · pocoo`,
    description: post.meta.description,
    prefix: "../",
    ogType: "article",
  })}
<body>
  <main class="post">
    <p class="back"><a href="../index.html">&larr; all posts</a></p>
    <header class="post-head">
      <h1>${esc(post.meta.title)}</h1>
      <p class="meta"><time datetime="${esc(post.meta.date)}">${displayDate(post.meta.date)}</time></p>
      ${tagsHtml(post.meta.tags)}
    </header>
    <article class="prose">
${bodyHtml}
    </article>
  </main>
  ${telemetryScript(true, post.slug, post.meta.title)}
</body>
</html>`;
}

// ── Index page ────────────────────────────────────────────────────────────────
function renderIndex(posts) {
  const entries = posts.map((p) => `      <li class="entry">
        <h2 class="entry-title"><a href="posts/${esc(p.slug)}.html">${esc(p.meta.title)}</a></h2>
        <p class="meta"><time datetime="${esc(p.meta.date)}">${displayDate(p.meta.date)}</time></p>
        <p class="entry-desc">${esc(p.meta.description || "")}</p>
        ${tagsHtml(p.meta.tags)}
      </li>`).join("\n");

  return `${head({
    title: "pocoo",
    description: "Technical writing on agentic systems, protocols, and building in public.",
    prefix: "",
    ogType: "website",
  })}
<body>
  <main class="index">
    <header class="index-head">
      <h1>pocoo</h1>
      <p class="lede">Technical writing on agentic systems, protocols, and building in public.</p>
    </header>
    <ul class="post-list">
${entries}
    </ul>
  </main>
  ${telemetryScript(false, null, null)}
</body>
</html>`;
}

// ── Atom feed ─────────────────────────────────────────────────────────────────
function renderFeed(posts) {
  const updated = posts.length > 0
    ? `${posts[0].meta.date}T00:00:00Z`
    : new Date().toISOString();
  const entries = posts.map((p) => `  <entry>
    <title>${esc(p.meta.title)}</title>
    <link href="https://pocoo.vaked.dev/posts/${esc(p.slug)}.html"/>
    <id>https://pocoo.vaked.dev/posts/${esc(p.slug)}.html</id>
    <updated>${esc(p.meta.date)}T00:00:00Z</updated>
    <summary type="text">${esc(p.meta.description || "")}</summary>
  </entry>`).join("\n");

  return `<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>pocoo</title>
  <link href="https://pocoo.vaked.dev/feed.xml" rel="self" type="application/atom+xml"/>
  <link href="https://pocoo.vaked.dev/"/>
  <updated>${updated}</updated>
  <id>https://pocoo.vaked.dev/</id>
${entries}
</feed>`;
}

// ── Main ──────────────────────────────────────────────────────────────────────
async function main() {
  await rm(DIST_DIR, { recursive: true, force: true });
  await mkdir(path.join(DIST_DIR, "posts"), { recursive: true });

  const files = (await readdir(POSTS_DIR))
    .filter((f) => f.toLowerCase().endsWith(".md"))
    .sort();

  const posts = [];
  let skipped = 0;
  for (const file of files) {
    const raw = await readFile(path.join(POSTS_DIR, file), "utf8");
    const { meta, body } = parseFrontmatter(raw);
    if (meta.draft === true) { skipped++; console.log(`skip (draft): ${file}`); continue; }
    posts.push({ slug: slugOf(file), meta, body });
  }

  posts.sort((a, b) => String(b.meta.date).localeCompare(String(a.meta.date)));

  for (const post of posts) {
    const html = renderPost(post);
    await writeFile(path.join(DIST_DIR, "posts", `${post.slug}.html`), html, "utf8");
    console.log(`render: posts/${post.slug}.html`);
  }

  await writeFile(path.join(DIST_DIR, "index.html"), renderIndex(posts), "utf8");
  console.log("render: index.html");

  await writeFile(path.join(DIST_DIR, "feed.xml"), renderFeed(posts), "utf8");
  console.log("render: feed.xml");

  await cp(path.join(ROOT, "assets"), path.join(DIST_DIR, "assets"), { recursive: true });
  if (existsSync(path.join(ROOT, "_headers"))) {
    await cp(path.join(ROOT, "_headers"), path.join(DIST_DIR, "_headers"));
  }
  console.log("copy: assets, _headers -> dist/");
  console.log(`\ndone: ${posts.length} post(s), ${skipped} draft(s) skipped.`);
}

main().catch((err) => { console.error(err); process.exit(1); });
```

- [ ] **Step 2: Run build with no posts — verify it doesn't crash**

```bash
cd /Users/lodripeter/workspace/peterlodri-sec/pocoo.vaked.dev
node build.mjs
```

Expected output:
```
render: index.html
render: feed.xml
copy: assets, _headers -> dist/

done: 0 post(s), 0 draft(s) skipped.
```

`dist/index.html` and `dist/feed.xml` should exist.

- [ ] **Step 3: Verify feed.xml is valid Atom with 0 entries**

```bash
cat dist/feed.xml
```

Expected: valid XML with `<feed>` root, `<title>pocoo</title>`, no `<entry>` elements.

- [ ] **Step 4: Write a smoke-test post and verify it renders**

Create `/Users/lodripeter/workspace/peterlodri-sec/pocoo.vaked.dev/posts/2026-06-23-hello-world.md`:

```markdown
---
title: "Hello World"
date: 2026-06-23
tags: [test]
description: "First post smoke test."
draft: false
---

This is a test post. It should render correctly.

## A heading

Some prose with `inline code` and a code block:

```python
print("hello from pocoo")
```
```

- [ ] **Step 5: Run build and verify post renders**

```bash
node build.mjs
```

Expected:
```
render: posts/2026-06-23-hello-world.html
render: index.html
render: feed.xml
copy: assets, _headers -> dist/

done: 1 post(s), 0 draft(s) skipped.
```

Check `dist/posts/2026-06-23-hello-world.html` exists and contains `<h1>Hello World</h1>` and the telemetry script.

- [ ] **Step 6: Delete smoke-test post**

```bash
rm posts/2026-06-23-hello-world.md
```

- [ ] **Step 7: Commit build.mjs**

```bash
git add build.mjs
git commit -m "feat: build.mjs — markdown renderer, Atom RSS, telemetry injection"
```

---

## Task 4: Write _headers

**Files:**
- Create: `pocoo.vaked.dev/_headers`

- [ ] **Step 1: Write _headers**

Create `/Users/lodripeter/workspace/peterlodri-sec/pocoo.vaked.dev/_headers`:

```
/*
  X-Content-Type-Options: nosniff
  X-Frame-Options: SAMEORIGIN
  Referrer-Policy: strict-origin-when-cross-origin
  Content-Security-Policy: default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src https://chat.vaked.dev; base-uri 'none'; form-action 'none'

/feed.xml
  Content-Type: application/atom+xml; charset=utf-8
```

- [ ] **Step 2: Commit**

```bash
git add _headers
git commit -m "feat: _headers — CSP + feed.xml content-type"
```

---

## Task 5: Update ultrawhale HF manifest

**Files:**
- Modify: `ultrawhale/site/hf-dataset-card.md`
- Modify: `ultrawhale/.github/workflows/hf-publish.yml`

- [ ] **Step 1: Add pocoo.vaked.dev to dataset card site table**

In `/Users/lodripeter/workspace/peterlodri-sec/ultrawhale/site/hf-dataset-card.md`, find the Sources table and add a row:

```markdown
| [pocoo.vaked.dev](https://pocoo.vaked.dev) | Personal technical blog |
```

The table currently has rows for chat.vaked.dev, music.vaked.dev, beat.vaked.dev, protocol.vaked.dev, irc.vaked.dev. Add pocoo.vaked.dev after irc.

- [ ] **Step 2: Add pocoo.vaked.dev to hf-publish.yml sources array**

In `/Users/lodripeter/workspace/peterlodri-sec/ultrawhale/.github/workflows/hf-publish.yml`, find the line:

```
"sources": ["chat.vaked.dev", "protocol.vaked.dev", "music.vaked.dev", "beat.vaked.dev", "irc.vaked.dev", "vaked.dev/ultrawhale"]
```

Replace with:

```
"sources": ["chat.vaked.dev", "protocol.vaked.dev", "music.vaked.dev", "beat.vaked.dev", "irc.vaked.dev", "pocoo.vaked.dev", "vaked.dev/ultrawhale"]
```

- [ ] **Step 3: Add pocoo.vaked.dev to MANIFEST links object**

In the same file, find:

```
"irc": "https://irc.vaked.dev"
```

Add after it:

```
"pocoo": "https://pocoo.vaked.dev"
```

(Note: add a trailing comma to the irc line first.)

- [ ] **Step 4: Commit ultrawhale changes**

```bash
cd /Users/lodripeter/workspace/peterlodri-sec/ultrawhale
git add site/hf-dataset-card.md .github/workflows/hf-publish.yml
git commit -m "feat(hf): add pocoo.vaked.dev to telemetry sources + dataset card"
git push origin main
```

---

## Task 6: GitHub repo + Cloudflare Pages setup

- [ ] **Step 1: Create GitHub repo**

```bash
cd /Users/lodripeter/workspace/peterlodri-sec/pocoo.vaked.dev
gh repo create peterlodri-sec/pocoo.vaked.dev --public --source=. --remote=origin
git push -u origin main
```

- [ ] **Step 2: Connect Cloudflare Pages**

In Cloudflare dashboard:
1. Workers & Pages → Create → Pages → Connect to Git
2. Select repo `peterlodri-sec/pocoo.vaked.dev`
3. Build settings:
   - Framework preset: None
   - Build command: `node build.mjs`
   - Build output directory: `dist`
4. Save and Deploy

- [ ] **Step 3: Add custom domain**

In the Pages project → Custom domains → Add `pocoo.vaked.dev`.
Cloudflare will auto-add the DNS record (CF proxy ON).

- [ ] **Step 4: Verify deployment**

```bash
curl -sI https://pocoo.vaked.dev | head -5
curl -sI https://pocoo.vaked.dev/feed.xml | grep content-type
```

Expected:
```
HTTP/2 200
...
content-type: application/atom+xml; charset=utf-8
```

---

## Self-Review

**Spec coverage check:**
- ✅ Repo structure (Task 1)
- ✅ blog.css protocol.vaked.dev aesthetic (Task 2)
- ✅ build.mjs: frontmatter, draft filter, post rendering, index, RSS (Task 3)
- ✅ Atom feed with all posts (Task 3 `renderFeed`)
- ✅ Telemetry: page_view, post_read (45s, post-only), session_end (Task 3 `telemetryScript`)
- ✅ `_headers` with CSP + feed.xml content-type (Task 4)
- ✅ HF dataset card + manifest updated (Task 5)
- ✅ Deployment instructions (Task 6)

**Placeholder scan:** None found. All code blocks are complete.

**Type consistency:** `telemetryScript(isPost, slug, title)` called consistently in `renderPost` (true, post.slug, post.meta.title) and `renderIndex` (false, null, null). `renderFeed(posts)` called in main. All function names match usage.

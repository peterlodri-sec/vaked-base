# pocoo.vaked.dev — Design Spec

**Date:** 2026-06-23
**Status:** Approved

## Summary

Personal technical blog at `pocoo.vaked.dev`. Minimal aesthetic matching protocol.vaked.dev. Forked from `crabcc.app-blog` build pipeline, dropping the crabcc design system in favour of self-contained CSS. Atom RSS feed. Tier 2 telemetry feeding the ultrawhale HF dataset.

Reference: https://lucumr.pocoo.org/ — minimal, content-first personal tech blog.

---

## 1. Structure

New repo: `peterlodri-sec/pocoo.vaked.dev`

```
pocoo.vaked.dev/
  posts/                    ← markdown posts, YYYY-MM-DD-slug.md
  assets/
    blog.css                ← protocol.vaked.dev aesthetic, no _ds dependency
  build.mjs                 ← forked from crabcc.app-blog, adapted
  _headers                  ← Cloudflare Pages headers
  package.json              ← single dep: markdown-it
  dist/                     ← generated output, not committed
    index.html
    feed.xml
    posts/<slug>.html
```

No `_ds/` design system. No build toolchain beyond Node + `markdown-it`.

### Post frontmatter (unchanged from crabcc)

```yaml
---
title: "Post title"
date: 2026-06-23
tags: [tag1, tag2]
description: "One-sentence summary shown in index and feed."
draft: false
---
```

---

## 2. CSS Aesthetic

Single `assets/blog.css`. Protocol.vaked.dev CSS vars:

```css
:root {
  --bg:      #070b16;
  --surface: #0a0a14;
  --card:    #14141f;
  --fg:      #e0e8f5;
  --accent:  #00d4ff;   /* cyan — links, h1, site title */
  --green:   #00e660;   /* h2 section headers */
  --dim:     #6878a0;   /* dates, meta, tags */
  --border:  #26304a;
  --warn:    #ffb020;   /* tag pills */
}
body {
  font-family: ui-monospace, SFMono-Regular, 'SF Mono', Consolas, monospace;
  background: var(--bg);
  color: var(--fg);
  max-width: 860px;
  margin: 0 auto;
  padding: 2rem 1rem;
  line-height: 1.7;
}
```

**Index page:** site title "pocoo" in `--accent`, minimal post list. Each entry: title (cyan link) + date (dim) + description. No sidebar, no images.

**Post page:** `← all posts` back link, `<h1>` cyan, date in dim below title, prose body `--fg`. Code blocks: `--card` background, `--green` text. No comments.

---

## 3. RSS (Atom 1.0)

Generated as `dist/feed.xml` by `build.mjs`. All posts included.

```xml
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>pocoo</title>
  <link href="https://pocoo.vaked.dev/feed.xml" rel="self"/>
  <link href="https://pocoo.vaked.dev/"/>
  <updated>{most recent post ISO date}</updated>
  <id>https://pocoo.vaked.dev/</id>
  <entry>
    <title>{post title}</title>
    <link href="https://pocoo.vaked.dev/posts/{slug}.html"/>
    <id>https://pocoo.vaked.dev/posts/{slug}.html</id>
    <updated>{date}T00:00:00Z</updated>
    <summary type="text">{description}</summary>
  </entry>
  ...
</feed>
```

Every page `<head>` includes:
```html
<link rel="alternate" type="application/atom+xml" title="pocoo" href="/feed.xml">
```

---

## 4. Telemetry + HF Pipeline

Inline `<script>` injected at bottom of `<body>` by `build.mjs` for every page. Same Tier 2 pattern as music.vaked.dev and irc.vaked.dev. No PII.

### Events

| event | trigger | payload |
|---|---|---|
| `page_view` | page load | `slug`, `title`, `page: 'pocoo.vaked.dev'` |
| `post_read` | 45s on a post page | `slug`, `read_duration_sec: 45` |
| `session_end` | `beforeunload` | `duration_sec`, `page` |

`post_read` fires only on post pages (`/posts/...`), not the index.

### Destination

`POST https://chat.vaked.dev/api/telemetry` → Cloudflare Function → HuggingFace dataset `PeetPedro/ultrawhale-dogfood/telemetry/`

### HF manifest updates (ultrawhale repo)

- `site/hf-dataset-card.md`: add `pocoo.vaked.dev` row to site table
- `.github/workflows/hf-publish.yml`: add `pocoo.vaked.dev` to telemetry sources array and MANIFEST links

---

## 5. Deployment

**Platform:** Cloudflare Pages
**Build command:** `node build.mjs`
**Output dir:** `dist`
**Custom domain:** `pocoo.vaked.dev`
**DNS:** CF proxy ON — Cloudflare Pages handles TLS

### `_headers`

```
/*
  X-Content-Type-Options: nosniff
  X-Frame-Options: SAMEORIGIN
  Referrer-Policy: strict-origin-when-cross-origin
  Content-Security-Policy: default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src https://chat.vaked.dev; base-uri 'none'; form-action 'none'

/feed.xml
  Content-Type: application/atom+xml; charset=utf-8
```

`/feed.xml` requires explicit `Content-Type` override — CF Pages defaults to `text/xml`.

No environment variables required.

---

## 6. Build Changes vs crabcc.app-blog

Changes to `build.mjs`:

| what | change |
|---|---|
| `_ds` references | remove entirely |
| `head()` function | use `<link rel="stylesheet" href="${prefix}assets/blog.css">` only |
| Site title | `"pocoo"` |
| Index lede | `"Technical writing on agentic systems, protocols, and building in public."` |
| `renderIndex()` | remove `ds-eyebrow` component ref |
| RSS | add `renderFeed(posts)` → `dist/feed.xml` |
| Telemetry | add `telemetryScript(isPost, slug, title)` injected into every page |
| `<head>` | add `<link rel="alternate" ...>` for feed |

---

## Out of Scope

- Comments
- Search
- Pagination (unlikely to need with a personal blog volume)
- Author photo / about page (can add later)
- GitHub Actions CI (Cloudflare Pages auto-deploys on push)

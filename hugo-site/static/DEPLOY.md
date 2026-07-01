# vaked.dev — Deployment Manifest

> **Domain:** vaked.dev
> **Hosting:** Cloudflare Pages
> **Source:** This directory (`deploy/vaked.dev/`)
> **Deployed:** 2026-06-16 · Genesis Ceremony day

---

## File Structure

```
vaked.dev/                     ← Cloudflare Pages root
├── index.html                 ← Landing page (hero + genesis seal + docs)
├── README.md                  ← Public repo README
├── _headers                   ← Cloudflare Pages security/cache headers
├── genesis/                   ← Genesis Archive (the 5 sealed files)
│   ├── genesis_block_00.md    ← Immutable Root Integrity Kernel
│   ├── GRAVEYARD.md           ← Honesty ledger
│   ├── genesis_reflection.md  ← Session distillation
│   ├── genesis_snapshot.md    ← Cryptographic pre-lock proof
│   └── HONEST_BEGINNINGS.md   ← Full ceremony transcript
├── research/                  ← Research documentation package
│   ├── RESEARCH_SUMMARY.md    ← Executive overview for researchers
│   ├── MASTER_RESEARCH_INDEX.md ← 120+ artifact catalog
│   ├── CROSS_REFERENCE_MAP.md   ← Doc interconnect graph
│   └── genesis_summary.html   ← Visual overview for non-technical reviewers
└── .gitignore
```

---

## Deployment

### Option A: Cloudflare Pages (recommended)

1. Push this directory as a Git repository to GitHub
2. Connect the repo to Cloudflare Pages
3. Set build settings:
   - **Build command:** (none — static site)
   - **Build output directory:** `/` (root)
   - **Root directory:** `/`
4. Set custom domain: `vaked.dev`
5. Deploy

### Option B: Direct Upload (Wrangler CLI)

```bash
cd deploy/vaked.dev
npx wrangler pages deploy . --project-name=vaked-dev --branch=main
```

### Option C: Any Static Host

This is a static site. Deploy the contents of `deploy/vaked.dev/` to any
static hosting service (Netlify, Vercel, GitHub Pages, S3 + CloudFront,
nginx on vakedos, etc.).

---

## DNS Notarization

The Genesis Seal Hash is notarized in the DNS TXT record of `vaked.dev`.
This was set by the operator (Peter Lodri) on 2026-06-16 during the Genesis
Ceremony. The TXT record is independent of this deployment — it lives in DNS,
not in any file. This provides out-of-band verification.

```
dig TXT vaked.dev +short | grep vaked-genesis-seal
# Expected: vaked-genesis-seal=7c242080f5f821e5eaf563fe2208d60632c451687baf65f4fe8e4a0d226e3ecf
```

---

## Post-Deployment Verification

After deploying, verify:

- [ ] `https://vaked.dev/` loads the landing page
- [ ] `https://vaked.dev/genesis/genesis_block_00.md` returns the immutable kernel
- [ ] `https://vaked.dev/research/RESEARCH_SUMMARY.md` returns the research summary
- [ ] `dig TXT vaked.dev +short` returns the genesis seal TXT record
- [ ] Local `shasum -a 256` of the 5 genesis files matches the DNS TXT record
- [ ] `_headers` cache rules are active (check response headers)

---

## Genesis Seal Verification (Public)

Any visitor can verify the seal by running:

```bash
curl -sL https://vaked.dev/genesis/genesis_block_00.md \
        https://vaked.dev/genesis/GRAVEYARD.md \
        https://vaked.dev/genesis/genesis_reflection.md \
        https://vaked.dev/genesis/genesis_snapshot.md \
        https://vaked.dev/genesis/HONEST_BEGINNINGS.md \
  | shasum -a 256
# Compare with: dig TXT vaked.dev +short | grep vaked-genesis-seal
```

---

## Signed

```
Genesis Seal: 7c242080f5f821e5eaf563fe2208d60632c451687baf65f4fe8e4a0d226e3ecf
Domain:       vaked.dev
Operator:     Peter Lodri
Witness:      Gemini (orchestrator) + DeepSeek-v4-pro (sealing agent)
Location:     Tatabánya, Hungary
Date:         2026-06-16
```

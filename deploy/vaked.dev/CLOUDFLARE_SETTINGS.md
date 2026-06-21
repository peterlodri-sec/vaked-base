# Cloudflare Zone Settings — vaked.dev (Free Tier, Recommended)

> Apply these in Cloudflare Dashboard → vaked.dev →  
> SSL/TLS, Security, Speed, Network, Scrape Shield

---

## SSL/TLS → Edge Certificates

| Setting | Value | Why |
|---------|-------|-----|
| SSL/TLS encryption mode | **Full (strict)** | Requires valid cert on origin. Pages provides this. |
| Always Use HTTPS | **On** | Redirect all HTTP → HTTPS |
| HTTP Strict Transport Security (HSTS) | **Enabled** (handled by `_headers`) | Already set: max-age=63072000; includeSubDomains; preload |
| Minimum TLS Version | **1.2** | Drop TLS 1.0/1.1 |
| Opportunistic Encryption | **On** | |
| TLS 1.3 | **On** | |
| Automatic HTTPS Rewrites | **On** | Fixes mixed content |
| Certificate Transparency Monitoring | **On** | |

---

## Security → Settings

| Setting | Value | Why |
|---------|-------|-----|
| Security Level | **Medium** | Challenge threats, allow legit traffic |
| Challenge Passage | **30 minutes** | |
| Browser Integrity Check | **On** | |

---

## Security → Bots

| Setting | Value | Why |
|---------|-------|-----|
| Bot Fight Mode | **On** | Free tier. Blocks verified bots. |
| Block AI Scrapers/Crawlers | **On** (if available on free) | |

---

## Speed → Optimization

| Setting | Value | Why |
|---------|-------|-----|
| Auto Minify (JS/CSS/HTML) | **Off** | Static site — we serve clean source. Minification can break inline CSS. |
| Brotli | **On** | Best compression, free |
| Early Hints | **On** | Preloads resources before page arrives |
| Rocket Loader | **Off** | Breaks static sites. We don't need JS optimization. |

---

## Network

| Setting | Value | Why |
|---------|-------|-----|
| HTTP/2 | **On** (default) | Multiplexed connections |
| HTTP/3 (with QUIC) | **On** | Faster handshake, better on lossy networks |
| 0-RTT Connection Resumption | **On** | Faster repeat visits |
| IPv6 Compatibility | **On** (default) | |
| gRPC | **Off** | Not needed |
| WebSockets | **On** | Future use |

---

## Scrape Shield

| Setting | Value | Why |
|---------|-------|-----|
| Email Address Obfuscation | **On** | Obfuscates `peter.lodri@gmail.com` in genesis_block_00.md |
| Server-side Excludes | **Off** | Not needed |
| Hotlink Protection | **Off** | We want hotlinks to markdown/docs |

---

## Caching → Configuration

| Setting | Value | Why |
|---------|-------|-----|
| Caching Level | **Standard** | |
| Browser Cache TTL | **Respect Existing Headers** | We set Cache-Control in `_headers` |
| Crawler Hints | **On** | Helps search engines |

---

## DNS → Settings

| Setting | Value | Why |
|---------|-------|-----|
| DNSSEC | **On** (if available on free) | Protects against DNS spoofing |
| CNAME Flattening | **Flatten at root** (default) | |

---

## Analytics (free tier)

| Setting | Value |
|---------|-------|
| Web Analytics | **Enable** (if available on free tier) |

---

## Rules (free tier allows 5)

If available, add:

| Rule | Type | Value |
|------|------|-------|
| Security Level: High for `/genesis/*` | WAF Custom Rule | Protects sealed files |
| Cache Level: Cache Everything for `/*.md` | Cache Rule | Force-edge-cache markdown docs |

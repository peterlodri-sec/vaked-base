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

# Deployment plan: Vaked docs site → Hetzner (NixOS, existing proxy)

Plan to deploy **PR #90** (self-hosted Astro Starlight docs site under `site/`) to the
existing NixOS Hetzner host that already serves public services behind a reverse proxy
with TLS. Docs to live at a dedicated subdomain.

Status: **plan only — nothing deployed.** Generated 2026-06-13.

## What we are deploying

- A **purely static** HTML bundle (Astro Starlight: 53 pages, Pagefind client-side
  search). No server-side runtime, no database, no open ports of its own.
- Produced reproducibly by `nix build .#docs` (the `packages.docs` output PR #90 adds
  to `flake.nix`) → a Nix store path of static files. Equivalent npm path: `cd site &&
  npm run build` → `site/dist/`.
- Source of truth stays the repo Markdown; `site/scripts/sync-docs.mjs` regenerates
  content at build time.

## Target (confirmed)

| Dimension | Answer |
|-----------|--------|
| Host | Existing **NixOS** Hetzner machine |
| Topology | **Existing reverse proxy + TLS** already fronts other public services — docs is a new vhost |
| URL | **Dedicated subdomain** (exact hostname: _TBD — fill in_) |

## Recommended approach (Nix-native, on-brand)

Consume `vaked-base` as a **flake input** in the host's NixOS configuration and serve
`vaked-base.packages.<system>.docs` as the static root of a new vhost on the existing
proxy. TLS reuses the host's existing ACME setup. This keeps "Vaked declares, Nix
materializes": the deployed bytes are the reproducible build output, and a docs update
is just a flake-input bump + `nixos-rebuild switch` (rollback = previous generation).

Alternative (lighter, less on-brand): build `dist/` in CI and `rsync` it to a web root
the proxy already serves. Use only if you do **not** want the host to evaluate this
flake. The rest of this plan assumes the Nix-native path.

**Assumption that gates execution:** the existing proxy is **NixOS-managed Caddy or
nginx** (`services.caddy` / `services.nginx`). On a NixOS host that is the idiomatic
setup, but it is unconfirmed. If the proxy is **Traefik**, or runs **outside NixOS**
(Docker labels, a hand-rolled config), the `virtualHosts` integration below does not
slot in and the serving mechanism changes — confirm which proxy and how it is managed
before step 2.

## Prerequisites (block any deploy — do these first)

1. **PR #90 is `CONFLICTING`.** Resolve conflicts (expect `flake.nix` `packages` block
   + `README.md`) and merge to `main`, so the host can pin a clean `main` rev. (Or pin
   the flake input directly at the PR head commit — but merging first is cleaner.)
2. **Set the real origin.** `site/astro.config.mjs` has `site: 'https://docs.vaked.example'`
   (placeholder). Change it to the chosen subdomain **before the build** — it drives
   canonical URLs, the sitemap, and Pagefind base paths. This is a code change in the
   PR; patch it before merge.
3. **Verify `nix build .#docs` on the target arch.** **Verified green on
   `aarch64-darwin` during planning** (exit 0 → 53 HTML pages, `pagefind/` search index,
   `404.html`, pretty-URL deep pages, 5.8M bundle). `importNpmLock` fetched per-platform
   **prebuilt** `sharp`/`esbuild`/`rollup` tarballs (no libvips compile), so the hermetic
   build holds. The host is `x86_64-linux` (or `aarch64-linux`); the build is
   platform-parameterized (`forAllSystems`) so a linux build should be equivalent —
   confirm once on a linux builder, low risk.
4. **DNS.** Create the subdomain `A`/`AAAA` record → host IP. (Provider unknown; wherever
   the existing services' DNS lives.)

## Deploy steps (NixOS host, existing proxy)

> These edits land in **the host's NixOS config** (a separate infra repo or `/etc/nixos`),
> NOT in `vaked-base`. Exact file paths depend on that repo's layout — _confirm where the
> host config lives and how it is pushed (nixos-rebuild over SSH / deploy-rs / colmena)._

1. Add the flake input (pin a rev/tag, do not float `main`):

   ```nix
   # host flake.nix
   inputs.vaked-base.url = "github:peterlodri-sec/vaked-base/<pinned-rev-or-tag>";
   ```

2. Thread `inputs` into the host system and bind the built docs:

   ```nix
   nixosConfigurations.<host> = nixpkgs.lib.nixosSystem {
     specialArgs = { inherit inputs; };
     modules = [ ./hosts/<host>.nix ];
   };
   ```

   ```nix
   # ./hosts/<host>.nix
   { pkgs, inputs, ... }:
   let docs = inputs.vaked-base.packages.${pkgs.stdenv.hostPlatform.system}.docs;
   in {
     # --- if the existing proxy is Caddy (most likely — PR ships a Caddyfile) ---
     services.caddy.virtualHosts."docs.<your-domain>".extraConfig = ''
       root * ${docs}
       encode zstd gzip
       file_server
       try_files {path} {path}/ {path}.html =404
       handle_errors {
         rewrite * /404.html
         file_server
       }
     '';
   }
   ```

   If the existing proxy is **nginx** instead, use:

   ```nix
   services.nginx.virtualHosts."docs.<your-domain>" = {
     enableACME = true;
     forceSSL = true;
     root = "${docs}";
     locations."/" = {
       tryFiles = "$uri $uri/ $uri.html =404";
       extraConfig = "error_page 404 /404.html;";
     };
   };
   ```

   (ACME terms/email and Caddy's email are already configured if other vhosts use TLS —
   just add the block. Caddy provisions the cert on first request once DNS resolves;
   nginx+ACME provisions on activation.)

3. Push the change the way this host is already deployed (`nixos-rebuild switch
   --flake .#<host>`, or `deploy-rs`/`colmena` — match existing practice).

4. **Verify after activation:**
   - `curl -I https://docs.<your-domain>/` → `200`, valid TLS.
   - A deep link (pretty URL), e.g. `/docs/language/0011-type-system/` → `200` (proves
     the `try_files` rule).
   - Pagefind search loads (`/pagefind/pagefind.js` → `200`) and returns results.
   - A bogus path → custom `404.html`.

## Update / redeploy model

- Docs change → bump the `vaked-base` input pin on the host (`nix flake update
  vaked-base` or repin to a new tag) → `nixos-rebuild switch`. Reproducible; rollback is
  the previous NixOS generation.
- **Follow-up, not built now:** a CI job (GitHub Action) to auto-bump the host pin or
  push on merge to `main`. Default is manual one-shot. Decide later.

## Open inputs needed to make this exact

1. Exact docs subdomain (`docs.<your-domain>`).
2. Which reverse proxy the host runs (Caddy vs nginx) — determines which block above.
3. Where the host NixOS config lives + how it is pushed (repo path, rebuild mechanism).
4. DNS provider (for the subdomain record).

## Risk register

| Risk | Severity | Mitigation |
|------|----------|------------|
| PR #90 `CONFLICTING`, not merged | Blocker | Resolve + merge before pinning the input |
| `nix build .#docs` not yet run on linux | Low | **Verified green on darwin** (53 pages, search, 404, pretty URLs); prebuilt sharp tarballs = no native compile; re-run once on a linux builder |
| `site:` placeholder → wrong canonicals/sitemap | Med | Patch `astro.config.mjs` before build |
| Deploy mechanism unknown | Med | Match existing host push workflow before editing |
| Static bundle exposes dotfiles | Low | Caddy/nginx `file_server` over the Nix store path serves only built output; no secrets in the bundle |
| Build runs on the host at rebuild time | Low/Med | A `nixos-rebuild` referencing `vaked-base.packages.<system>.docs` builds ~359 derivations **on the host**, needing npm + GitHub egress during rebuild. Given the project's deny-by-default-egress leanings: build on a separate builder or push to a binary cache, or ensure rebuild-time egress is open |
| Resource footprint | Low | Static files only; negligible CPU/RAM; no new listening port behind the existing proxy |

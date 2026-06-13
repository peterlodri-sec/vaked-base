# Vaked docs site

A self-hosted documentation site for `vaked-base`, built with
[Astro Starlight](https://starlight.astro.build/) — actively maintained by the
Astro core team, MIT-licensed, deeply themeable, with built-in client-side
search ([Pagefind](https://pagefind.app/)).

## How it works

The repo's Markdown is the **single source of truth**. A prebuild step,
[`scripts/sync-docs.mjs`](scripts/sync-docs.mjs), generates the Starlight content
into `src/content/docs/` (gitignored, regenerated on every build) **without ever
editing the sources**. It:

1. Copies `../docs`, `../vaked`, `../protocol` into the content collection.
2. Injects a `title:` frontmatter from each file's first `# H1` (and strips that
   H1 so it isn't rendered twice). Starlight requires a title; the source files
   stay plain.
3. Lowercases output paths so routes are deterministic.
4. Rewrites relative links: targets inside the doc surface become local routes;
   everything else (e.g. `../../tools/…`, source files) becomes an absolute
   GitHub URL — so no internal link dangles. `npm run build` fails the build on
   any broken internal link (via `starlight-links-validator`).

## Commands

```bash
npm install           # once
npm run dev           # sync + dev server with HMR  → http://localhost:4321
npm run build         # sync + static build         → dist/
npm run preview       # preview the built dist/
```

From the repo root with Nix:

```bash
nix build .#docs      # reproducible static build   → result/
```

## Theming

Deep theming lives in three places:

- [`src/styles/theme.css`](src/styles/theme.css) — Vaked brand palette via
  Starlight's `--sl-color-*` custom properties (teal accent + amber).
- [`src/components/Footer.astro`](src/components/Footer.astro) — a component
  override (extends Starlight's default footer with the Vaked mantra).
- [`astro.config.mjs`](astro.config.mjs) — logo, sidebar, social links, plugins.

Add more component overrides under the `components` map in `astro.config.mjs`
(see [Starlight overrides](https://starlight.astro.build/guides/overriding-components/)).

## Self-hosting

Build, then serve the static `dist/` (or the Nix `result/`) with any static
server. A [`Caddyfile`](Caddyfile) is included:

```bash
npm run build
caddy run --config Caddyfile     # → http://localhost:8788
```

Point its `root` at `dist/` (or the Nix build output) and swap the `:8788` block
for your domain to get automatic HTTPS.

## Note: upstream maintenance

Starlight was chosen over the otherwise-excellent **Material for MkDocs** because
the latter entered maintenance mode in late 2025 (security fixes only). If the
Python/MkDocs lineage is preferred later, **Zensical** (Material's successor that
reads `mkdocs.yml`) is the migration path once it stabilizes — it was still alpha
as of mid-2026.

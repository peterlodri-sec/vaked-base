# vaked · sentinel console

the sentinel console is the live operator surface (`vaked-ide`) that watches the
vakefield agent runtime: a flat, hairline, JetBrains-Mono / violet-indigo chrome
over a plain-JS simulation (`window.VakedConsole`) — graph, sparks, phases —
rendered by a React/Babel UI (header, rail, terminal, inspector, tour). this
directory is the vendored, decomposed source of the captured prototype. the
prototype is the **spec**, not disposable: the split below is behavior-preserving
(concatenating the split files reproduces the prototype's css/js/jsx). this is a
vendor + decompose step only — no build, no productionization yet (see `SPEC.md`).

## file map

| path | what |
|------|------|
| `index.html` | the shell: head links (DS tokens + console chrome), `#root` mount + boot loader, pinned React/Babel CDN tags, and `<script>` refs to the split files below |
| `console.css` | extracted console chrome (`<style>` block from the prototype) |
| `engine.js` | plain-JS simulation defining `window.VakedConsole` (graph + sparks + phases) |
| `ui.jsx` | React/Babel chrome (header, rail, terminal, inspector, tour) — `type="text/babel"` |
| `_ds/` | vendored vaked design system: `styles.css` (entry, `@import`s the tokens), `tokens/*.css` (fonts, colors, typography, spacing, syntax, kinds), `_ds_bundle.js` (component bundle), `_ds_manifest.json`, `_adherence.oxlintrc.json`, `readme.md` |
| `assets/logo-mark.png` | the wordmark used by the header; `ui.jsx` reads `window.__resources.logo` and falls back to this path |
| `SPEC.md` | the `appendSystemPrompt` frontend-engineer agent brief (the productionization spec) |

## pinned runtime

`index.html` pins (do not upgrade — productionization is a later task):

- `react@18.3.1` umd development build (unpkg)
- `react-dom@18.3.1` umd development build (unpkg)
- `@babel/standalone@7.29.0` (unpkg)

the integrity (SRI) hashes on these tags are the exact ones the prototype carried;
they were verified against the canonical unpkg files byte-for-byte.

## origin

vendored from two artifacts that were captured upstream and then removed once fully
unpacked here:

- `web/design-system-export.zip` — the bound vaked design system (`_ds/`), plus the
  decomposed `vaked-console/` reference files and the appendSystemPrompt spec.
- `web/sentinel-console-prototype.html` — a ~2.7MB self-rehydrating "bundler" page
  whose `__bundler/template` held the real document and whose `__bundler/manifest`
  held the inlined React/Babel/bundle/engine/ui resources. those resources decode to
  the split files in this directory (the `_ds_bundle.js` and `engine.js` are
  byte-identical to the design-system export; `console.css` and the DS tokens match;
  `ui.jsx` is the prototype-embedded variant with the `window.__resources.logo`
  fallback).

## NEVER BUILD ON THE DEVELOPER MACHINE

per repo policy (`CLAUDE.md`): no build / compile / link / package step runs on the
developer machine. builds go to `dev-cx53` (linux, nix) or github actions. this
decomposition task needed none — it is file extraction + splitting only.

// sync-docs.mjs — generate Starlight content from the repo's source docs.
//
// Source of truth: ../docs, ../vaked, ../protocol (plain Markdown, NEVER edited).
// This script copies those trees into src/content/docs/ (gitignored, wiped each
// run) and applies the transforms Starlight needs, WITHOUT touching the sources:
//
//   1. Inject a `title:` frontmatter derived from each file's first H1 (and strip
//      that H1 so it isn't rendered twice — Starlight renders the title as the H1).
//   2. Lowercase every output path so routes are deterministic (Starlight slugs
//      mirror the on-disk id; lowercasing removes any case ambiguity).
//   3. Rewrite relative links: targets that map to a synced page become local
//      routes; everything else (e.g. ../../tools/…, source files, missing
//      targets) becomes an absolute GitHub URL so no internal link dangles.
//   4. Emit a splash landing page at / (src/content/docs/index.md).

import { readdir, readFile, writeFile, mkdir, rm } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SITE_DIR = path.resolve(fileURLToPath(import.meta.url), '../..');
const REPO_ROOT = path.resolve(SITE_DIR, '..');
const OUT_ROOT = path.join(SITE_DIR, 'src', 'content', 'docs');

// Directory trees (relative to repo root) that make up the doc surface.
const SOURCE_DIRS = ['docs', 'vaked', 'protocol'];
const GITHUB_BLOB = 'https://github.com/peterlodri-sec/vaked-base/blob/main';
const MD_EXT = /\.(md|mdx|markdown)$/i;

/** Recursively collect every Markdown file under `dir` (absolute paths). */
async function collectMarkdown(dir) {
  const out = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const abs = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...(await collectMarkdown(abs)));
    else if (entry.isFile() && MD_EXT.test(entry.name)) out.push(abs);
  }
  return out;
}

/** repo-relative POSIX path, e.g. docs/language/0011-type-system.md */
const repoRel = (abs) => path.relative(REPO_ROOT, abs).split(path.sep).join('/');

/** Map a synced source file to its Starlight route, e.g. /docs/language/0011-type-system/ */
const toRoute = (rel) => '/' + rel.toLowerCase().replace(MD_EXT, '') + '/';

/** Is this repo-relative path inside the synced doc surface? */
const inSurface = (rel) => SOURCE_DIRS.some((d) => rel === d || rel.startsWith(d + '/'));

function extractTitle(body, fallback) {
  const lines = body.split('\n');
  for (let i = 0; i < lines.length; i++) {
    const m = /^#\s+(.+?)\s*#*\s*$/.exec(lines[i]);
    if (m) {
      lines.splice(i, 1); // strip the H1 so Starlight doesn't render two
      // also drop a single trailing blank line left behind
      if (lines[i] === '') lines.splice(i, 1);
      return { title: m[1].trim(), body: lines.join('\n') };
    }
  }
  return { title: fallback, body };
}

const isExternal = (t) =>
  /^[a-z]+:/i.test(t) || t.startsWith('//') || t.startsWith('#') || t.startsWith('mailto:');

/** Rewrite a single link target found in a file living at `srcAbs`. */
function rewriteTarget(target, srcAbs) {
  if (isExternal(target)) return target;
  if (target.startsWith('/')) return target; // already site-absolute

  const hashIdx = target.indexOf('#');
  const hash = hashIdx >= 0 ? target.slice(hashIdx) : '';
  const pathPart = hashIdx >= 0 ? target.slice(0, hashIdx) : target;
  if (!pathPart) return target; // pure anchor handled above, but be safe

  const abs = path.resolve(path.dirname(srcAbs), pathPart);
  const rel = repoRel(abs);

  // Inside the synced surface and a Markdown page that exists → local route.
  if (inSurface(rel) && MD_EXT.test(rel) && existsSync(abs)) {
    return toRoute(rel) + hash;
  }
  // Anything else that lives in the repo → link to it on GitHub.
  if (!rel.startsWith('..')) {
    return `${GITHUB_BLOB}/${rel}${hash}`;
  }
  // Escapes the repo entirely — leave untouched.
  return target;
}

/** Rewrite all inline + reference-style Markdown links in `body`. */
function rewriteLinks(body, srcAbs) {
  // inline: ](target) and ][ref] style — match the (target) form, incl images
  body = body.replace(/(!?\]\()([^)\s]+)(\s+"[^"]*")?(\))/g, (_, open, target, title, close) => {
    return open + rewriteTarget(target, srcAbs) + (title || '') + close;
  });
  return body;
}

const yamlEscape = (s) => '"' + s.replace(/\\/g, '\\\\').replace(/"/g, '\\"') + '"';

async function run() {
  await rm(OUT_ROOT, { recursive: true, force: true });
  await mkdir(OUT_ROOT, { recursive: true });

  let count = 0;
  for (const dir of SOURCE_DIRS) {
    const abs = path.join(REPO_ROOT, dir);
    if (!existsSync(abs)) continue;
    for (const srcAbs of await collectMarkdown(abs)) {
      const rel = repoRel(srcAbs);
      const raw = await readFile(srcAbs, 'utf8');
      const stem = path.basename(rel).replace(MD_EXT, '');
      const { title, body } = extractTitle(raw, stem);
      const rewritten = rewriteLinks(body, srcAbs);

      const outRel = rel.toLowerCase();
      const outAbs = path.join(OUT_ROOT, outRel);
      await mkdir(path.dirname(outAbs), { recursive: true });
      const frontmatter = `---\ntitle: ${yamlEscape(title)}\n---\n\n`;
      await writeFile(outAbs, frontmatter + rewritten);
      count++;
    }
  }

  await writeFile(path.join(OUT_ROOT, 'index.md'), SPLASH);
  console.log(`sync-docs: wrote ${count} pages + splash → ${path.relative(REPO_ROOT, OUT_ROOT)}`);
}

const SPLASH = `---
title: Vaked
description: The foundation monorepo for the Vaked agentic-runtime ecosystem.
template: splash
hero:
  tagline: A flake-native capability-graph language for agentic, native, mesh-aware, parallel systems.
  actions:
    - text: Project context
      link: /docs/context/project_context/
      icon: right-arrow
      variant: primary
    - text: Language manifesto
      link: /docs/language/0001-language-manifesto/
      icon: open-book
    - text: View on GitHub
      link: https://github.com/peterlodri-sec/vaked-base
      icon: external
      variant: minimal
---

> Vaked declares. Nix materializes. OTP supervises. Zig enforces. eBPF testifies. CrabCC indexes. Surfaces reveal.

Vaked compiles a typed semantic capability-graph into ordinary Nix flakes, NixOS
modules, Zig daemon configs, eBPF policy manifests, OpenTelemetry config,
generated docs, and CrabCC indexes.

This site is generated from the repository's \`docs/\`, \`vaked/\`, and \`protocol/\`
trees — the Markdown in the repo is the single source of truth.
`;

run().catch((err) => {
  console.error(err);
  process.exit(1);
});

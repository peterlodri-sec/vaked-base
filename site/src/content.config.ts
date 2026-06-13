import { defineCollection } from 'astro:content';
import { docsLoader } from '@astrojs/starlight/loaders';
import { docsSchema } from '@astrojs/starlight/schema';

// Content is generated into src/content/docs/ by scripts/sync-docs.mjs (run
// automatically by `npm run dev` / `npm run build`). Sources live in ../docs,
// ../vaked, ../protocol and are never edited.
export const collections = {
  docs: defineCollection({ loader: docsLoader(), schema: docsSchema() }),
};

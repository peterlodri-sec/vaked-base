// @ts-check
import { defineConfig, passthroughImageService } from 'astro/config';
import starlight from '@astrojs/starlight';
import starlightLinksValidator from 'starlight-links-validator';

// Self-hosted documentation site for vaked-base.
// Content is synced from ../docs, ../vaked, ../protocol — see scripts/sync-docs.mjs.
export default defineConfig({
  // Set this to the public origin when deploying (used for canonical URLs + sitemap).
  site: 'https://docs.vaked.example',
  // No raster image processing needed (the only asset is an SVG logo); using the
  // passthrough service avoids the `sharp` native dependency, which keeps the
  // Nix build (packages.docs) hermetic.
  image: { service: passthroughImageService() },
  integrations: [
    starlight({
      title: 'Vaked',
      tagline: 'A flake-native capability-graph language',
      logo: { src: './src/assets/logo.svg', alt: 'Vaked' },
      favicon: '/favicon.svg',
      customCss: ['./src/styles/theme.css'],
      social: [
        {
          icon: 'github',
          label: 'GitHub',
          href: 'https://github.com/peterlodri-sec/vaked-base',
        },
      ],
      // Deep-theming hook: override the footer to carry the Vaked mantra.
      components: {
        Footer: './src/components/Footer.astro',
      },
      plugins: [starlightLinksValidator()],
      sidebar: [
        {
          label: 'Language',
          autogenerate: { directory: 'docs/language' },
        },
        {
          label: 'Project context',
          autogenerate: { directory: 'docs/context' },
        },
        {
          label: 'Runtime',
          autogenerate: { directory: 'docs/runtime' },
        },
        {
          label: 'Protocol',
          items: [
            { label: 'Overview', autogenerate: { directory: 'docs/protocol' } },
            { label: 'RFCs', autogenerate: { directory: 'protocol/rfcs' } },
          ],
        },
        {
          label: 'Decisions',
          autogenerate: { directory: 'docs/decisions' },
        },
        {
          label: 'Superpowers',
          autogenerate: { directory: 'docs/superpowers' },
        },
        {
          label: 'Vaked (language source)',
          autogenerate: { directory: 'vaked' },
        },
      ],
    }),
  ],
});

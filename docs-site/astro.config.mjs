// SPDX-License-Identifier: Apache-2.0
import { defineConfig } from 'astro/config'
import starlight from '@astrojs/starlight'
import { SIGNAL, signalOn } from './src/signal.mjs'

const site = 'https://docs.conversationsimulator.com'

// Signal's web client (src/signal.mjs): journeys after a yes, on top of the
// depth ladder. This site has no consent form of its own, so the script asks
// in its own small banner. Only in the deploy workflow's production build.
const signalHead = signalOn(site)
  ? [
      {
        tag: 'script',
        attrs: {
          defer: true,
          src: SIGNAL.script,
          'data-key': SIGNAL.key,
          'data-ingest': SIGNAL.ingest,
          'data-studio': SIGNAL.studio.join(' '),
          'data-privacy': SIGNAL.privacy,
        },
      },
    ]
  : []

// Remark plugin: honor explicit heading IDs written as `## Title {#custom-id}`.
// Astro/Starlight's default Markdown pipeline does NOT support this syntax — it
// slugifies the literal braces into the id (e.g. `foo {#foo}` -> `foo-foo`),
// which silently breaks every in-app deep link into the troubleshooting page
// (e.g. troubleshooting/#engine-startup-failure). We strip the trailing `{#id}`
// token from the heading text and set the id explicitly so those anchors — and
// the remediation-card check-id anchors (#disk-space, #llm-present, …) — resolve.
// Headings are always top-level blocks in Markdown, so iterating the root's
// direct children is sufficient (no recursive tree walk needed).
function remarkExplicitHeadingIds() {
  return (tree) => {
    for (const node of tree.children) {
      if (node.type !== 'heading' || !node.children || node.children.length === 0) continue
      const last = node.children[node.children.length - 1]
      if (!last || last.type !== 'text') continue
      const match = last.value.match(/^(.*?)\s*\{#([\w-]+)\}\s*$/)
      if (!match) continue
      last.value = match[1]
      node.data = node.data || {}
      node.data.hProperties = { ...(node.data.hProperties || {}), id: match[2] }
      node.data.id = match[2]
    }
  }
}

// Public documentation for Conversation Simulator, deployed to
// https://docs.conversationsimulator.com by .github/workflows/deploy-website.yml.
// Content lives in src/content/docs/ — adapted for players, creators, and
// contributors from the engineering docs in /docs.
export default defineConfig({
  site,
  markdown: {
    remarkPlugins: [remarkExplicitHeadingIds],
  },
  // Redirect old URLs so links in shipped app versions don't break.
  redirects: {
    '/play/local-models/': '/play/ai-engine/',
  },
  integrations: [
    starlight({
      title: 'Conversation Simulator',
      description:
        'Documentation for Conversation Simulator — the simulator for conversations. Practice interviews, negotiations, language, and difficult conversations with AI characters that run entirely on your computer.',
      logo: {
        src: './src/assets/logo.svg',
        alt: 'Conversation Simulator',
      },
      favicon: '/favicon.svg',
      social: [
        {
          icon: 'github',
          label: 'GitHub',
          href: 'https://github.com/outrightmental/ConversationSimulator',
        },
      ],
      editLink: {
        baseUrl: 'https://github.com/outrightmental/ConversationSimulator/edit/main/docs-site/',
      },
      customCss: ['./src/styles/custom.css'],
      // SkipLink is the first thing in <body>: the override puts Signal's depth
      // ladder ahead of it (src/components/SkipLink.astro).
      components: {
        SkipLink: './src/components/SkipLink.astro',
      },
      lastUpdated: true,
      sidebar: [
        { label: 'Getting Started', autogenerate: { directory: 'start' } },
        { label: 'Playing', autogenerate: { directory: 'play' } },
        { label: 'Creating Packs', autogenerate: { directory: 'create' } },
        { label: 'Safety & Privacy', autogenerate: { directory: 'trust' } },
        { label: 'Reference', autogenerate: { directory: 'reference' } },
        { label: 'Project', autogenerate: { directory: 'project' } },
        {
          label: 'Development',
          autogenerate: { directory: 'dev' },
          collapsed: true,
        },
      ],
      head: [
        // favicon.svg is Starlight's own `favicon` above; these two are for
        // what does not read SVG favicons: anything that asks for
        // /favicon.ico without reading the page, and iOS's home screen.
        // All three come from publishing/assets/source/gen_icons.py.
        { tag: 'link', attrs: { rel: 'icon', href: '/favicon.ico', sizes: '32x32' } },
        { tag: 'link', attrs: { rel: 'apple-touch-icon', href: '/apple-touch-icon.png' } },
        {
          tag: 'meta',
          attrs: { property: 'og:image', content: 'https://www.conversationsimulator.com/images/og-card.png' },
        },
        ...signalHead,
      ],
    }),
  ],
})

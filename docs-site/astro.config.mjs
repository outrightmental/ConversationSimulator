// SPDX-License-Identifier: Apache-2.0
import { defineConfig } from 'astro/config'
import starlight from '@astrojs/starlight'

// Public documentation for Conversation Simulator, deployed to
// https://docs.conversationsimulator.com by .github/workflows/deploy-website.yml.
// Content lives in src/content/docs/ — adapted for players, creators, and
// contributors from the engineering docs in /docs.
export default defineConfig({
  site: 'https://docs.conversationsimulator.com',
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
        {
          tag: 'meta',
          attrs: { property: 'og:image', content: 'https://www.conversationsimulator.com/images/og-card.png' },
        },
      ],
    }),
  ],
})

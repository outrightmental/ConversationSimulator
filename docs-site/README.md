<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# docs-site — docs.conversationsimulator.com

The public documentation site for Conversation Simulator, built with
[Astro Starlight](https://starlight.astro.build/). This site is the
**canonical user-facing documentation** — the app and website link here, not
to the GitHub repository or wiki.

## Develop

```bash
pnpm install
pnpm --filter @convsim/docs-site dev      # http://localhost:4321
pnpm --filter @convsim/docs-site build    # output in docs-site/dist/
```

## Content layout

Content lives in `src/content/docs/`, one directory per sidebar section:

| Directory    | Sidebar section  | Audience |
| ------------ | ---------------- | -------- |
| `start/`     | Getting Started  | Players installing and running the app |
| `play/`      | Playing          | Players using models, voice, packs |
| `create/`    | Creating Packs   | Scenario and pack authors |
| `trust/`     | Safety & Privacy | Everyone — the local-first promise and safety system |
| `reference/` | Reference        | Architecture, spec, schemas, adapters |
| `project/`   | Project          | Roadmap, contributing, beta testing |
| `dev/`       | Development      | Contributors and release engineering |

Sidebar entries are auto-generated per directory; order pages with
`sidebar.order` in frontmatter.

## Relationship to /docs

Pages here are **adapted** from the engineering docs in `/docs` for a public
audience. When you change behaviour documented in both places, update both.
The app links to specific pages and anchors here (see
`apps/web/src` and `services/convsim-core/convsim_core/routers/preflight.py`) —
do not rename these slugs without updating the app:

- `/start/install/`, `/start/quickstart/`, `/start/troubleshooting/`
  (anchors `#engine-startup-failure`, `#port-conflicts` must keep working)
- `/play/local-models/` (the app's "Setup guide" target for a missing inference engine)
- `/create/scenario-authoring/`, `/create/pack-validation/`,
  `/create/quality-bar/`, `/create/sample-pack/`
- `/project/beta-testing/`

## Deployment

Pushed to S3 + CloudFront by `.github/workflows/deploy-website.yml` on every
push to `main`. Infrastructure is defined in `/infra`.

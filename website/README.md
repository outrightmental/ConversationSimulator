<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# website — conversationsimulator.com

The public marketing site for Conversation Simulator, built with
[Hugo](https://gohugo.io/) (extended edition, pinned at 0.145.0 in CI). No
external theme — layouts and styles are bespoke and live entirely in this
folder.

## Develop

```bash
hugo server -s website          # from the repo root, http://localhost:1313
hugo --minify -s website        # production build into website/public/
```

## Layout

| Path | What it is |
| ---- | ---------- |
| `content/` | Page content: home (`_index.md`), `manifesto.md`, `download.md` |
| `layouts/` | Bespoke templates — homepage sections live in `layouts/index.html` |
| `assets/css/main.css` | The whole design system (Hugo Pipes: minified + fingerprinted) |
| `static/images/screenshots/` | Copies of `docs/assets/screenshots/*.svg` — refresh when those change |

The palette mirrors the app UI (see `docs/brand.md` and `apps/web/src`):
violet `#a78bfa` is the player's voice, emerald `#6ee7b7` is the character's,
amber marks scenario events. Copy follows the tone guide in `docs/brand.md` —
authoritative, warm, concrete; we own the category and never compare the
product to other genres.

## Deployment

Pushed to S3 + CloudFront by `.github/workflows/deploy-website.yml` on every
push to `main`. Infrastructure (DNS, buckets, certificates, deploy role) is
defined in `/infra`. The docs site is a separate build in `/docs-site`,
served at docs.conversationsimulator.com.

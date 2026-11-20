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
| `data/channels.yaml` | Every place to get the app — the stores for the full app and the free demo, and the source — with each one's status (`available`, `wishlist`, `soon`). Rendered by `layouts/partials/channels.html` on the home page (`#get`) and, through the `{{< channels >}}` shortcode, on `/download/`. When a store goes live, change its status here |
| `static/images/screenshots/` | Web copies of `docs/assets/screenshots/*.png` at 1×, 256 colours — refresh when those change (see `docs/screenshots.md`) |

The palette mirrors the app UI (see `docs/brand.md` and `apps/web/src`):
violet `#a78bfa` is the player's voice, emerald `#6ee7b7` is the character's,
amber marks scenario events. Copy follows the tone guide in `docs/brand.md` —
authoritative, warm, concrete; we own the category and never compare the
product to other genres.

## Analytics

The app sends nothing; this site is measured. **Signal**, Outright Mental's
own analytics (`params.signal` in `hugo.toml`), counts how far each page is
read from a ladder of 1×1 images that `layouts/partials/signal-ladder.html`
puts first inside every `<body>` (no script, cookie or id), and its web
client (`layouts/partials/signal.html`, loaded from signal.outright.io) keeps
a journey only after a visitor's yes in its own banner. Both render only in
the deploy workflow's build (`SIGNAL_DEPLOY=production`, see
`layouts/partials/signal-on.html`), never under `hugo server` or a local
build. Google Analytics (`[services.googleAnalytics]`) also runs on
production builds. What visitors are told is on the docs site's privacy page,
under *These websites*: keep it true when either changes.

## Deployment

Pushed to S3 + CloudFront by `.github/workflows/deploy-website.yml` on every
push to `main`. Infrastructure (DNS, buckets, certificates, deploy role) is
defined in `/infra`. The docs site is a separate build in `/docs-site`,
served at docs.conversationsimulator.com.

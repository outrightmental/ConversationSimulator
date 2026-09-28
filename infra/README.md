<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# infra — conversationsimulator.com

Terraform for everything the public website and docs site run on:

| Resource | Purpose |
| -------- | ------- |
| Route 53 hosted zone | DNS for `conversationsimulator.com` (domain registered at GoDaddy, delegated here) |
| ACM certificate (us-east-1) | TLS for apex + `www` + `docs`, DNS-validated |
| S3 buckets ×2 | Private origins for the marketing site and the docs site |
| CloudFront ×2 | CDN for `conversationsimulator.com` (+`www` redirect) and `docs.conversationsimulator.com` |
| CloudFront Function | `www` → apex 301 + pretty-URL `index.html` rewrites |
| IAM OIDC role | Lets GitHub Actions (main branch only) deploy — no stored AWS keys |
| GitHub repository | The repo itself (adopted via import block), the Actions **secrets** the website deploy workflow reads, and the Actions **variables** the Steam deploy workflow reads |

The deploy workflow is [.github/workflows/deploy-website.yml](../.github/workflows/deploy-website.yml);
its secrets (`AWS_DEPLOY_ROLE_ARN`, `AWS_REGION`, `SITE_BUCKET`, `DOCS_BUCKET`,
`SITE_CLOUDFRONT_DISTRIBUTION_ID`, `DOCS_CLOUDFRONT_DISTRIBUTION_ID`) are
created by this configuration — never set them by hand.

The Steam deploy workflow is [.github/workflows/steam-deploy.yml](../.github/workflows/steam-deploy.yml);
the Valve App and depot IDs it reads (`STEAM_APP_ID`, `STEAM_DEPOT_*_ID`,
`STEAM_DEMO_APP_ID`, `STEAM_DEMO_DEPOT_*_ID`) are repository **variables**
declared in `local.steam_variables` in `github.tf`. Change a value there and
apply — never in the GitHub UI or with `gh variable set`. A variable that was
created by hand is adopted by the `import` block next to the resource, so the
first plan after adding it shows an import, not a create. The Steam upload
credentials (`STEAM_USERNAME`, `STEAM_CONFIG_VDF`) are not set yet; when they
are, they belong in `github.tf` too, as `github_actions_secret` resources fed
from sensitive Terraform variables.

## Prerequisites

- Terraform ≥ 1.7
- AWS credentials for the target account (Route 53, ACM, S3, CloudFront, IAM)
- `GITHUB_TOKEN` env var — a token for `outrightmental` with **administration**,
  **secrets** and **variables** read/write on the repository

## DNS reality during the domain lease

`conversationsimulator.com` is **leased through GoDaddy/Afternic**. Until the
lease converts to full ownership:

- The registry's NS records are controlled by Afternic (initially
  `ns*.afternic.com` parking, then flipped to the buyer's GoDaddy DNS zone at
  `ns59/ns60.domaincontrol.com`). The GoDaddy DCC shows *"this domain is
  registered elsewhere"* and the zone's NS records are not editable.
- Therefore Route 53 **cannot be made authoritative yet**, and because GoDaddy
  DNS has no ALIAS/ANAME support, the bare apex cannot point at CloudFront.
- **www.conversationsimulator.com is the canonical host.** The apex forwards
  to it (GoDaddy forwarding / the CloudFront function also 301s apex→www).

Records that must exist in the **GoDaddy DNS zone**
(dcc.godaddy.com → DNS for the domain):

| Type | Name | Value |
| ---- | ---- | ----- |
| CNAME | `www` | `site_distribution_domain` output |
| CNAME | `docs` | `docs_distribution_domain` output |
| CNAME | ACM validation names (×3) | ACM validation values — `terraform output acm_validation_records` |
| Forwarding | `@` | 301 → `https://www.conversationsimulator.com` |

The Route 53 zone and its records are still provisioned so that the day the
lease allows custom nameservers (ask Afternic support to set the four values
in the `name_servers` output), everything cuts over with zero changes.

## Bootstrap (first apply)

```bash
cd infra
terraform init

# 1. Certificate first — validation stays PENDING until the GoDaddy zone is
#    live at the registry AND the validation CNAMEs exist there.
terraform apply -target=aws_acm_certificate.site
terraform output acm_validation_records   # add these CNAMEs in GoDaddy DCC

# 2. Once the certificate shows ISSUED (aws acm list-certificates
#    --region us-east-1), apply the rest:
terraform apply

# 3. Point www/docs CNAMEs in GoDaddy at the two *_distribution_domain
#    outputs, and set apex forwarding to https://www.conversationsimulator.com.
```

The first full apply also **imports the GitHub repository** (see the `import`
block in `github.tf`) — review that part of the plan carefully the first
time; it should show adoption plus settings alignment, not recreation. Note
that `has_wiki = false` is deliberate: the docs site replaced the wiki.

After the apply, commit `.terraform.lock.hcl` so provider versions are pinned
for everyone.

## Verify

```bash
terraform output site_distribution_domain   # open https://<value> before DNS is live
dig +short NS conversationsimulator.com     # should return the Route 53 set
curl -sI https://conversationsimulator.com | head -1          # HTTP/2 200 (after first deploy)
curl -sI https://www.conversationsimulator.com/download/ | head -1   # HTTP/2 301 → apex
curl -sI https://docs.conversationsimulator.com | head -1     # HTTP/2 200
```

Then trigger the deploy workflow (push to `main` touching `website/` or
`docs-site/`, or run it manually from the Actions tab) to publish content.

## Notes

- **State** is local (`terraform.tfstate`, gitignored). For team use, move to
  the S3 backend stub in `versions.tf`.
- **OIDC provider**: an AWS account can hold only one provider for
  `token.actions.githubusercontent.com`. If this account already has one, set
  `create_oidc_provider = false`.
- **Buckets are never public** — public access blocks stay on; CloudFront
  reads through Origin Access Control.
- **Costs**: Route 53 zone ~$0.50/mo; S3 + CloudFront on this traffic profile
  are typically well under a dollar a month at PriceClass_100.

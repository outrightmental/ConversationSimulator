# SPDX-License-Identifier: Apache-2.0
# The repository itself is managed here, plus the Actions secrets the deploy
# workflow needs. The import block adopts the existing repository on the
# first apply instead of trying to create it.

import {
  to = github_repository.this
  id = var.github_repository
}

resource "github_repository" "this" {
  name         = var.github_repository
  description  = "The simulator for conversations — practice interviews, negotiations, language, and difficult conversations with AI characters that run 100% on your computer."
  homepage_url = "https://${var.domain_name}"

  visibility = "public"

  has_issues      = true
  has_discussions = true
  has_projects    = true
  # The docs site (docs.conversationsimulator.com) replaced the wiki; all
  # in-app and in-repo references now point there.
  has_wiki = false

  allow_merge_commit     = true
  allow_squash_merge     = true
  allow_rebase_merge     = true
  delete_branch_on_merge = true

  topics = [
    "conversation-practice",
    "local-first",
    "llm",
    "simulator",
    "speech-recognition",
  ]

  lifecycle {
    prevent_destroy = true
  }
}

# --- Actions secrets consumed by .github/workflows/deploy-website.yml ---

locals {
  deploy_secrets = {
    AWS_DEPLOY_ROLE_ARN             = aws_iam_role.deploy.arn
    AWS_REGION                      = var.aws_region
    SITE_BUCKET                     = aws_s3_bucket.static["site"].bucket
    DOCS_BUCKET                     = aws_s3_bucket.static["docs"].bucket
    SITE_CLOUDFRONT_DISTRIBUTION_ID = aws_cloudfront_distribution.site.id
    DOCS_CLOUDFRONT_DISTRIBUTION_ID = aws_cloudfront_distribution.docs.id
  }
}

resource "github_actions_secret" "deploy" {
  for_each = local.deploy_secrets

  repository      = github_repository.this.name
  secret_name     = each.key
  plaintext_value = each.value
}

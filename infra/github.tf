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
  has_discussions = false
  has_projects    = true
  # The docs site (docs.conversationsimulator.com) replaced the wiki; all
  # in-app and in-repo references now point there.
  has_wiki = false

  allow_merge_commit     = false
  allow_squash_merge     = true
  allow_rebase_merge     = false
  delete_branch_on_merge = true

  # Default squash commit = PR title + PR description (issue #460)
  squash_merge_commit_title   = "PR_TITLE"
  squash_merge_commit_message = "PR_BODY"

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

# --- Actions variables consumed by .github/workflows/steam-deploy.yml ---
#
# Non-secret Valve identifiers for the paid Steam app (STEAM_*) and its free
# Steam Next Fest demo app (STEAM_DEMO_*, issue #495). The same values are
# recorded in publishing/STEAM_APP_REGISTRATION.md. Change them here and
# apply — never in the GitHub UI or with `gh variable set`. The import block
# adopts a variable that already exists on the repository (all eight were
# first created by hand), so adding one here shows an import on the next plan
# rather than a failed create.

locals {
  steam_variables = {
    # Conversation Simulator — App 4963030 and its three platform depots
    STEAM_APP_ID           = "4963030"
    STEAM_DEPOT_WINDOWS_ID = "4963031"
    STEAM_DEPOT_MACOS_ID   = "4963032"
    STEAM_DEPOT_LINUX_ID   = "4963033"

    # Conversation Simulator Demo — App 5343430 and its three platform depots
    STEAM_DEMO_APP_ID           = "5343430"
    STEAM_DEMO_DEPOT_WINDOWS_ID = "5343431"
    STEAM_DEMO_DEPOT_MACOS_ID   = "5343432"
    STEAM_DEMO_DEPOT_LINUX_ID   = "5343433"
  }
}

import {
  for_each = local.steam_variables
  to       = github_actions_variable.steam[each.key]
  id       = "${var.github_repository}:${each.key}"
}

resource "github_actions_variable" "steam" {
  for_each = local.steam_variables

  repository    = github_repository.this.name
  variable_name = each.key
  value         = each.value
}

# Steam upload credentials (STEAM_USERNAME, STEAM_CONFIG_VDF) are not set: the
# steam job short-circuits while they are absent. When the CI build account is
# provisioned, declare them here as github_actions_secret resources fed from
# sensitive Terraform variables, exactly like local.deploy_secrets above —
# never create them in the GitHub UI or with `gh secret set`.

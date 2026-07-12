# SPDX-License-Identifier: Apache-2.0
# GitHub Actions deploys via OIDC — no long-lived AWS keys anywhere.
# The role below may only be assumed by workflows running on the main branch
# of the repository, and may only sync the two site buckets and invalidate
# the two distributions.

resource "aws_iam_openid_connect_provider" "github" {
  count = var.create_oidc_provider ? 1 : 0

  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]

  # AWS validates GitHub's OIDC cert chain against trusted roots and ignores
  # these values, but the argument is required by the API.
  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1c58a3a8518e8759bf075b76b750d4f2df264fcd",
  ]
}

data "aws_iam_openid_connect_provider" "github" {
  count = var.create_oidc_provider ? 0 : 1
  url   = "https://token.actions.githubusercontent.com"
}

locals {
  github_oidc_provider_arn = var.create_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : data.aws_iam_openid_connect_provider.github[0].arn
}

data "aws_iam_policy_document" "deploy_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.github_oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${local.repo_full}:ref:refs/heads/main"]
    }
  }
}

data "aws_iam_policy_document" "deploy_permissions" {
  statement {
    sid       = "ListSiteBuckets"
    actions   = ["s3:ListBucket"]
    resources = [for bucket in aws_s3_bucket.static : bucket.arn]
  }

  statement {
    sid = "WriteSiteObjects"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = [for bucket in aws_s3_bucket.static : "${bucket.arn}/*"]
  }

  statement {
    sid = "InvalidateDistributions"
    actions = [
      "cloudfront:CreateInvalidation",
      "cloudfront:GetInvalidation",
    ]
    resources = [
      aws_cloudfront_distribution.site.arn,
      aws_cloudfront_distribution.docs.arn,
    ]
  }
}

resource "aws_iam_role" "deploy" {
  name               = "convsim-website-deploy"
  description        = "GitHub Actions (main branch) deploys the website and docs site"
  assume_role_policy = data.aws_iam_policy_document.deploy_assume.json
}

resource "aws_iam_role_policy" "deploy" {
  name   = "deploy-static-sites"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy_permissions.json
}

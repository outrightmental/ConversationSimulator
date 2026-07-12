# SPDX-License-Identifier: Apache-2.0

variable "domain_name" {
  description = "Apex domain for the public website (leased at GoDaddy; DNS is delegated to the Route 53 zone this config creates)."
  type        = string
  default     = "conversationsimulator.com"
}

variable "docs_subdomain" {
  description = "Subdomain that serves the documentation site."
  type        = string
  default     = "docs"
}

variable "aws_region" {
  description = "Primary AWS region. CloudFront certificates always come from us-east-1 regardless of this value."
  type        = string
  default     = "us-east-1"
}

variable "github_owner" {
  description = "GitHub organization/user that owns the repository."
  type        = string
  default     = "outrightmental"
}

variable "github_repository" {
  description = "Repository name (without owner)."
  type        = string
  default     = "ConversationSimulator"
}

variable "create_oidc_provider" {
  description = "Create the GitHub Actions OIDC provider in this AWS account. Set to false if the account already has token.actions.githubusercontent.com registered (only one may exist per account)."
  type        = bool
  default     = true
}

locals {
  docs_domain = "${var.docs_subdomain}.${var.domain_name}"
  www_domain  = "www.${var.domain_name}"
  repo_full   = "${var.github_owner}/${var.github_repository}"

  common_tags = {
    Project   = "ConversationSimulator"
    ManagedBy = "terraform"
    Source    = "infra/"
  }
}

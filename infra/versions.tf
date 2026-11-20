# SPDX-License-Identifier: Apache-2.0

terraform {
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
    github = {
      source  = "integrations/github"
      version = "~> 6.5"
    }
  }

  # The studio's one state bucket, shared by every Outright Mental Terraform
  # root, each under a key of its own. This key is this project's and nobody
  # else's: never pass -migrate-state, never accept init's offer to copy state
  # into it. `use_lockfile` is S3-native locking (Terraform 1.10+).
  backend "s3" {
    bucket       = "outrightmental-terraform-state"
    key          = "conversationsimulator"
    region       = "us-east-1"
    use_lockfile = true
  }
}

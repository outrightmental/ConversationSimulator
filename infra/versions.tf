# SPDX-License-Identifier: Apache-2.0

terraform {
  required_version = ">= 1.7.0"

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

  # State is local by default (terraform.tfstate in this directory, gitignored).
  # For shared/team state, provision a state bucket once and uncomment:
  #
  # backend "s3" {
  #   bucket       = "convsim-terraform-state"
  #   key          = "website/terraform.tfstate"
  #   region       = "us-east-1"
  #   use_lockfile = true
  # }
}

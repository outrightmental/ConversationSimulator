# SPDX-License-Identifier: Apache-2.0

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }
}

# CloudFront only accepts ACM certificates issued in us-east-1.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = local.common_tags
  }
}

# Authenticates via the GITHUB_TOKEN environment variable (classic PAT or
# fine-grained token with repository administration + secrets permissions).
provider "github" {
  owner = var.github_owner
}

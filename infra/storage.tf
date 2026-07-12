# SPDX-License-Identifier: Apache-2.0
# Private S3 buckets for the two static sites. Nothing is public: CloudFront
# reads via Origin Access Control, and the deploy role writes via OIDC.

locals {
  # No dots in bucket names: CloudFront fetches the S3 REST origin over HTTPS,
  # and S3's *.s3.<region>.amazonaws.com wildcard certificate only matches a
  # single DNS label — a dotted bucket name fails TLS validation (502s).
  bucket_prefix = replace(var.domain_name, ".", "-")

  buckets = {
    site = "${local.bucket_prefix}-site"
    docs = "${local.bucket_prefix}-docs"
  }
}

resource "aws_s3_bucket" "static" {
  for_each = local.buckets

  bucket = each.value
}

resource "aws_s3_bucket_public_access_block" "static" {
  for_each = aws_s3_bucket.static

  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "static" {
  for_each = aws_s3_bucket.static

  bucket = each.value.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Keep old object versions around briefly for oops-recovery, then expire them.
resource "aws_s3_bucket_lifecycle_configuration" "static" {
  for_each = aws_s3_bucket.static

  bucket = each.value.id

  rule {
    id     = "expire-noncurrent"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 30
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

data "aws_iam_policy_document" "bucket_cloudfront" {
  for_each = local.buckets

  # GetObject for content; ListBucket so missing keys surface as 404 (not 403),
  # which lets CloudFront serve the custom 404 page correctly.
  statement {
    sid       = "AllowCloudFrontOAC"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.static[each.key].arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [each.key == "site" ? aws_cloudfront_distribution.site.arn : aws_cloudfront_distribution.docs.arn]
    }
  }

  statement {
    sid       = "AllowCloudFrontOACList"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.static[each.key].arn]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [each.key == "site" ? aws_cloudfront_distribution.site.arn : aws_cloudfront_distribution.docs.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "static" {
  for_each = aws_s3_bucket.static

  bucket = each.value.id
  policy = data.aws_iam_policy_document.bucket_cloudfront[each.key].json

  depends_on = [aws_s3_bucket_public_access_block.static]
}

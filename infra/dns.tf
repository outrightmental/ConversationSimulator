# SPDX-License-Identifier: Apache-2.0
# Route 53 hosted zone for conversationsimulator.com.
#
# The domain itself is registered at GoDaddy. After the first apply, point the
# GoDaddy nameservers at the values in the `name_servers` output (replace the
# NS set — do not add individual records at GoDaddy).

resource "aws_route53_zone" "primary" {
  name    = var.domain_name
  comment = "Public website + docs for Conversation Simulator (managed by infra/)"
}

# Apex -> website distribution
resource "aws_route53_record" "apex_a" {
  zone_id = aws_route53_zone.primary.zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = aws_cloudfront_distribution.site.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "apex_aaaa" {
  zone_id = aws_route53_zone.primary.zone_id
  name    = var.domain_name
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = aws_cloudfront_distribution.site.hosted_zone_id
    evaluate_target_health = false
  }
}

# www -> same distribution; a CloudFront Function 301s it to the apex.
resource "aws_route53_record" "www_a" {
  zone_id = aws_route53_zone.primary.zone_id
  name    = local.www_domain
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = aws_cloudfront_distribution.site.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "www_aaaa" {
  zone_id = aws_route53_zone.primary.zone_id
  name    = local.www_domain
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = aws_cloudfront_distribution.site.hosted_zone_id
    evaluate_target_health = false
  }
}

# docs -> documentation distribution
resource "aws_route53_record" "docs_a" {
  zone_id = aws_route53_zone.primary.zone_id
  name    = local.docs_domain
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.docs.domain_name
    zone_id                = aws_cloudfront_distribution.docs.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "docs_aaaa" {
  zone_id = aws_route53_zone.primary.zone_id
  name    = local.docs_domain
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.docs.domain_name
    zone_id                = aws_cloudfront_distribution.docs.hosted_zone_id
    evaluate_target_health = false
  }
}

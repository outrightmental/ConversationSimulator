# SPDX-License-Identifier: Apache-2.0
# One certificate covers the apex, www, and docs hostnames.
# DNS validation only completes after GoDaddy delegates to the Route 53
# nameservers — see infra/README.md for the two-step bootstrap.

resource "aws_acm_certificate" "site" {
  provider = aws.us_east_1

  domain_name = var.domain_name
  subject_alternative_names = [
    local.www_domain,
    local.docs_domain,
  ]
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.site.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  zone_id         = aws_route53_zone.primary.zone_id
  name            = each.value.name
  type            = each.value.type
  ttl             = 300
  records         = [each.value.record]
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "site" {
  provider = aws.us_east_1

  certificate_arn         = aws_acm_certificate.site.arn
  validation_record_fqdns = [for record in aws_route53_record.cert_validation : record.fqdn]
}

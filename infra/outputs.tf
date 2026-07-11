# SPDX-License-Identifier: Apache-2.0

output "name_servers" {
  description = "Route 53 nameservers — usable only when the domain lease allows custom NS at the registrar (ask Afternic support). Until then GoDaddy DNS serves the zone."
  value       = aws_route53_zone.primary.name_servers
}

output "acm_validation_records" {
  description = "CNAMEs that must exist in the live DNS zone (GoDaddy DCC during the lease) for the certificate to issue."
  value = [
    for dvo in aws_acm_certificate.site.domain_validation_options : {
      name  = dvo.resource_record_name
      type  = dvo.resource_record_type
      value = dvo.resource_record_value
    }
  ]
}

output "site_url" {
  value = "https://${local.www_domain}"
}

output "docs_url" {
  value = "https://${local.docs_domain}"
}

output "site_bucket" {
  value = aws_s3_bucket.static["site"].bucket
}

output "docs_bucket" {
  value = aws_s3_bucket.static["docs"].bucket
}

output "site_distribution_id" {
  value = aws_cloudfront_distribution.site.id
}

output "docs_distribution_id" {
  value = aws_cloudfront_distribution.docs.id
}

output "site_distribution_domain" {
  description = "CloudFront domain — useful for testing before DNS delegation."
  value       = aws_cloudfront_distribution.site.domain_name
}

output "docs_distribution_domain" {
  value = aws_cloudfront_distribution.docs.domain_name
}

output "deploy_role_arn" {
  description = "IAM role assumed by GitHub Actions via OIDC."
  value       = aws_iam_role.deploy.arn
}

output "certificate_arn" {
  value = aws_acm_certificate.site.arn
}

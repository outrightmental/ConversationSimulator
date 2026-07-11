# SPDX-License-Identifier: Apache-2.0
# CloudFront distributions: one for the marketing site (apex + www redirect),
# one for the docs site.

locals {
  # AWS managed cache policy "CachingOptimized"
  cache_policy_caching_optimized = "658327ea-f89d-4fab-a63d-7e88639e58f6"
  s3_origin_id                   = "s3-origin"
}

resource "aws_cloudfront_origin_access_control" "static" {
  name                              = "${var.domain_name}-oac"
  description                       = "OAC for Conversation Simulator static site buckets"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_function" "url_rewrite" {
  name    = "convsim-url-rewrite"
  runtime = "cloudfront-js-2.0"
  comment = "www redirect + pretty-URL index.html rewrite"
  publish = true
  code = templatefile("${path.module}/functions/url-rewrite.js.tftpl", {
    apex_domain = var.domain_name
  })
}

resource "aws_cloudfront_distribution" "site" {
  enabled             = true
  is_ipv6_enabled     = true
  http_version        = "http2and3"
  comment             = "conversationsimulator.com marketing site"
  default_root_object = "index.html"
  aliases             = [var.domain_name, local.www_domain]
  price_class         = "PriceClass_100"

  origin {
    domain_name              = aws_s3_bucket.static["site"].bucket_regional_domain_name
    origin_id                = local.s3_origin_id
    origin_access_control_id = aws_cloudfront_origin_access_control.static.id
  }

  default_cache_behavior {
    target_origin_id       = local.s3_origin_id
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    cache_policy_id        = local.cache_policy_caching_optimized

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.url_rewrite.arn
    }
  }

  custom_error_response {
    error_code            = 404
    response_code         = 404
    response_page_path    = "/404.html"
    error_caching_min_ttl = 60
  }

  custom_error_response {
    error_code            = 403
    response_code         = 404
    response_page_path    = "/404.html"
    error_caching_min_ttl = 60
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.site.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }
}

resource "aws_cloudfront_distribution" "docs" {
  enabled             = true
  is_ipv6_enabled     = true
  http_version        = "http2and3"
  comment             = "docs.conversationsimulator.com documentation site"
  default_root_object = "index.html"
  aliases             = [local.docs_domain]
  price_class         = "PriceClass_100"

  origin {
    domain_name              = aws_s3_bucket.static["docs"].bucket_regional_domain_name
    origin_id                = local.s3_origin_id
    origin_access_control_id = aws_cloudfront_origin_access_control.static.id
  }

  default_cache_behavior {
    target_origin_id       = local.s3_origin_id
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    cache_policy_id        = local.cache_policy_caching_optimized

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.url_rewrite.arn
    }
  }

  custom_error_response {
    error_code            = 404
    response_code         = 404
    response_page_path    = "/404.html"
    error_caching_min_ttl = 60
  }

  custom_error_response {
    error_code            = 403
    response_code         = 404
    response_page_path    = "/404.html"
    error_caching_min_ttl = 60
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.site.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }
}

resource "aws_cloudfront_cache_policy" "frontend" {
  name        = "${local.name}-frontend"
  default_ttl = 3600
  max_ttl     = 86400
  min_ttl     = 0
  parameters_in_cache_key_and_forwarded_to_origin {
    enable_accept_encoding_brotli = true
    enable_accept_encoding_gzip   = true
    cookies_config { cookie_behavior = "none" }
    headers_config { header_behavior = "none" }
    query_strings_config { query_string_behavior = "none" }
  }
}

data "aws_cloudfront_cache_policy" "api_disabled" {
  name = "Managed-CachingDisabled"
}
data "aws_cloudfront_origin_request_policy" "api" {
  name = "Managed-AllViewerExceptHostHeader"
}

resource "aws_cloudfront_distribution" "main" {
  enabled = true

  origin {
    domain_name = aws_lb.main.dns_name
    origin_id   = "alb"
    custom_header {
      name  = "X-Origin-Verify"
      value = random_password.cloudfront_origin_header.result
    }
    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id       = "alb"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = aws_cloudfront_cache_policy.frontend.id
  }

  ordered_cache_behavior {
    path_pattern             = "/api/*"
    target_origin_id         = "alb"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = data.aws_cloudfront_cache_policy.api_disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.api.id
  }

  restrictions {
    geo_restriction { restriction_type = "none" }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

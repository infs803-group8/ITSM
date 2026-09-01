output "alb_dns_name" { value = aws_lb.main.dns_name }
output "cloudfront_domain_name" { value = aws_cloudfront_distribution.main.domain_name }
output "backend_repository_url" { value = aws_ecr_repository.backend.repository_url }
output "frontend_repository_url" { value = aws_ecr_repository.frontend.repository_url }
output "attachment_bucket_name" { value = aws_s3_bucket.attachments.bucket }

# Consume the existing shared bucket without replacing its CORS or lifecycle.
data "aws_s3_bucket" "attachments" {
  bucket = var.attachment_bucket_name
}

provider "aws" {
  region = var.aws_region
}

resource "aws_s3_bucket" "development_attachments" {
  bucket = var.bucket_name
  tags = {
    Project     = "INFS803-ITSM"
    Environment = "development"
  }
}

resource "aws_s3_bucket_public_access_block" "development_attachments" {
  bucket                  = aws_s3_bucket.development_attachments.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "development_attachments" {
  bucket = aws_s3_bucket.development_attachments.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "development_attachments" {
  bucket = aws_s3_bucket.development_attachments.id
  rule {
    id     = "expire-development-objects"
    status = "Enabled"
    filter { prefix = "" }
    expiration { days = var.object_expiration_days }
  }
}

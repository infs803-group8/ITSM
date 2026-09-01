output "bucket_name" {
  value = aws_s3_bucket.development_attachments.bucket
}
output "bucket_arn" {
  value = aws_s3_bucket.development_attachments.arn
}

variable "aws_region" {
  type    = string
  default = "ap-southeast-2"
}
variable "bucket_name" {
  type        = string
  description = "Globally unique development attachment bucket name."
}
variable "object_expiration_days" {
  type    = number
  default = 30
}
variable "attachment_cors_allowed_origins" {
  type        = list(string)
  description = "Browser origins allowed to use presigned attachment URLs."
  default     = ["http://localhost:5173"]
}

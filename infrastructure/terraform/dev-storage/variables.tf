variable "aws_region" {
  type    = string
  default = "ap-southeast-2"
}
variable "bucket_name" {
  type        = string
  description = "Existing shared attachment bucket name; import before applying this stack."
  default     = "infs803-group8-dev-attachments-256329410824"
}
variable "object_expiration_days" {
  type    = number
  default = 30
}
variable "attachment_cors_allowed_origins" {
  type        = list(string)
  description = "Browser origins allowed to use presigned attachment URLs."
  default = [
    "http://localhost:5173", "http://127.0.0.1:5173",
    "https://infs803-group8.com", "https://www.infs803-group8.com"
  ]
}

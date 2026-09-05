variable "aws_region" {
  type    = string
  default = "ap-southeast-2"
}
variable "project_name" {
  type    = string
  default = "infs803-group8-itsm"
}
variable "database_name" {
  type    = string
  default = "service_desk"
}
variable "backend_image" {
  type        = string
  description = "Immutable backend ECR image URI."
}
variable "frontend_image" {
  type        = string
  description = "Immutable frontend ECR image URI."
}
variable "budget_email" {
  type      = string
  sensitive = true
}

variable "attachment_bucket_name" {
  type        = string
  description = "Existing shared private S3 bucket, managed outside this final stack."
  default     = "infs803-group8-dev-attachments-256329410824"
}
variable "attachment_public_base_url" {
  type    = string
  default = "https://s3.infs803-group8.com"
}
variable "attachment_key_prefix" {
  type    = string
  default = "attachments"
  validation {
    condition     = can(regex("^[A-Za-z0-9_-]+$", var.attachment_key_prefix))
    error_message = "Use a single nonempty S3 prefix without wildcards or slashes."
  }
}
variable "enable_attachment_cleanup" {
  type        = bool
  default     = false
  description = "Enable only after database bootstrap and cloud integration checks."
}
variable "enable_sla_monitor" {
  type        = bool
  default     = false
  description = "Enable only when Member C has implemented and verified the SLA job."
}

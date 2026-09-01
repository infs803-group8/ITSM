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

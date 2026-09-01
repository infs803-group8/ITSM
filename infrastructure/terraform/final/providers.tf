provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project     = "INFS803-ITSM"
      Environment = "final"
      ManagedBy   = "Terraform"
    }
  }
}

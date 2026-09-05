variable "github_oidc_provider_arn" {
  type        = string
  default     = null
  description = "Reuse an existing GitHub OIDC provider ARN; null creates it once in this account."
}
resource "aws_iam_openid_connect_provider" "github" {
  count          = var.github_oidc_provider_arn == null ? 1 : 0
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}
resource "aws_iam_role" "github_deploy" {
  name = "${local.name}-github-deploy"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow", Action = "sts:AssumeRoleWithWebIdentity"
      Principal = { Federated = var.github_oidc_provider_arn != null ? var.github_oidc_provider_arn : aws_iam_openid_connect_provider.github[0].arn }
      Condition = { StringEquals = {
        "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        "token.actions.githubusercontent.com:sub" = "repo:infs803-group8/ITSM:environment:final"
      } }
    }]
  })
}
resource "aws_iam_role_policy" "github_deploy" {
  role = aws_iam_role.github_deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken", "ecs:RegisterTaskDefinition", "ecs:DescribeTaskDefinition"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["ecr:DescribeImages", "ecr:BatchGetImage", "ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage"]
        Resource = [aws_ecr_repository.backend.arn, aws_ecr_repository.frontend.arn]
      },
      {
        Effect   = "Allow", Action = ["ecs:DescribeServices", "ecs:UpdateService"]
        Resource = [for service in aws_ecs_service.application : service.id]
      },
      {
        Effect    = "Allow", Action = ["ecs:RunTask"]
        Resource  = "${aws_ecs_task_definition.tasks["database-bootstrap"].arn_without_revision}:*"
        Condition = { ArnEquals = { "ecs:cluster" = aws_ecs_cluster.main.arn } }
      },
      {
        Effect   = "Allow", Action = ["ecs:DescribeTasks"]
        Resource = "arn:aws:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:task/${local.name}/*"
      },
      {
        Effect    = "Allow", Action = ["iam:PassRole"]
        Resource  = [aws_iam_role.ecs_execution.arn, aws_iam_role.backend_task.arn, aws_iam_role.scheduler.arn]
        Condition = { StringEquals = { "iam:PassedToService" = ["ecs-tasks.amazonaws.com", "scheduler.amazonaws.com"] } }
      },
      {
        Effect   = "Allow", Action = ["scheduler:GetSchedule", "scheduler:UpdateSchedule"]
        Resource = [for schedule in aws_scheduler_schedule.jobs : schedule.arn]
      },
      {
        Effect   = "Allow", Action = ["cloudfront:CreateInvalidation", "cloudfront:GetInvalidation"]
        Resource = aws_cloudfront_distribution.main.arn
      }
    ]
  })
}
output "github_deploy_role_arn" { value = aws_iam_role.github_deploy.arn }

resource "aws_iam_role" "ecs_execution" {
  name = "${local.name}-ecs-execution"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}
resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_caller_identity" "current" {}

resource "aws_iam_role_policy" "ecs_secrets" {
  role = aws_iam_role.ecs_execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow", Action = ["secretsmanager:GetSecretValue"]
      Resource = [aws_secretsmanager_secret.database.arn, aws_secretsmanager_secret.jwt.arn]
    }]
  })
}
resource "aws_iam_role" "backend_task" {
  name               = "${local.name}-backend-task"
  assume_role_policy = aws_iam_role.ecs_execution.assume_role_policy
}
resource "aws_iam_role_policy" "attachments" {
  role = aws_iam_role.backend_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = "${data.aws_s3_bucket.attachments.arn}/${var.attachment_key_prefix}/*"
      },
      {
        Effect    = "Allow", Action = ["s3:ListBucket"], Resource = data.aws_s3_bucket.attachments.arn
        Condition = { StringLike = { "s3:prefix" = ["${var.attachment_key_prefix}/*"] } }
      }
    ]
  })
}

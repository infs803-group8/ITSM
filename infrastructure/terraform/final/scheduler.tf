locals {
  schedules = {
    attachment-cleanup = { expression = "rate(30 minutes)", enabled = var.enable_attachment_cleanup }
    sla-monitor        = { expression = "rate(5 minutes)", enabled = var.enable_sla_monitor }
  }
}

resource "aws_iam_role" "scheduler" {
  name = "${local.name}-scheduler"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow", Action = "sts:AssumeRole"
      Principal = { Service = "scheduler.amazonaws.com" }
      Condition = {
        StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id }
        ArnEquals    = { "aws:SourceArn" = "arn:aws:scheduler:${var.aws_region}:${data.aws_caller_identity.current.account_id}:schedule-group/default" }
      }
    }]
  })
}
resource "aws_iam_role_policy" "scheduler" {
  role = aws_iam_role.scheduler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow", Action = ["ecs:RunTask"]
        Resource  = [for job in keys(local.schedules) : "${aws_ecs_task_definition.tasks[job].arn_without_revision}:*"]
        Condition = { ArnEquals = { "ecs:cluster" = aws_ecs_cluster.main.arn } }
      },
      {
        Effect    = "Allow", Action = ["iam:PassRole"]
        Resource  = [aws_iam_role.ecs_execution.arn, aws_iam_role.backend_task.arn]
        Condition = { StringEquals = { "iam:PassedToService" = "ecs-tasks.amazonaws.com" } }
      }
    ]
  })
}
resource "aws_scheduler_schedule" "jobs" {
  for_each            = local.schedules
  name                = "${local.name}-${each.key}"
  group_name          = "default"
  schedule_expression = each.value.expression
  state               = each.value.enabled ? "ENABLED" : "DISABLED"
  flexible_time_window { mode = "OFF" }
  target {
    arn      = aws_ecs_cluster.main.arn
    role_arn = aws_iam_role.scheduler.arn
    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.tasks[each.key].arn
      launch_type         = "FARGATE"
      platform_version    = "1.4.0"
      task_count          = 1
      network_configuration {
        subnets          = aws_subnet.public[*].id
        security_groups  = [aws_security_group.jobs.id]
        assign_public_ip = true
      }
    }
    retry_policy {
      maximum_event_age_in_seconds = 900
      maximum_retry_attempts       = 2
    }
  }
  lifecycle {
    ignore_changes = [target[0].ecs_parameters[0].task_definition_arn]
  }
  depends_on = [aws_iam_role_policy.scheduler]
}

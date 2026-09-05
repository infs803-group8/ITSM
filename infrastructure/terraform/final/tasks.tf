locals {
  task_commands = {
    backend            = ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
    frontend           = ["nginx", "-g", "daemon off;"]
    attachment-cleanup = ["python", "-m", "app.domains.attachments.cleanup_job"]
    database-bootstrap = ["python", "-m", "app.db.bootstrap"]
    sla-monitor        = ["python", "-m", "app.domains.sla.monitor_job"]
  }
  backend_environment = [
    { name = "ENVIRONMENT", value = "final" },
    { name = "AWS_REGION", value = var.aws_region },
    { name = "S3_BUCKET_NAME", value = data.aws_s3_bucket.attachments.id },
    { name = "S3_KEY_PREFIX", value = var.attachment_key_prefix },
    { name = "S3_PUBLIC_BASE_URL", value = var.attachment_public_base_url },
    { name = "CORS_ORIGINS", value = "https://${aws_cloudfront_distribution.main.domain_name}" }
  ]
  backend_secrets = [
    { name = "DATABASE_URL", valueFrom = "${aws_secretsmanager_secret.database.arn}:database_url::" },
    { name = "JWT_SECRET", valueFrom = aws_secretsmanager_secret.jwt.arn }
  ]
}

resource "aws_ecs_task_definition" "tasks" {
  for_each                 = local.task_commands
  family                   = "${local.name}-${each.key}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = each.key == "frontend" ? null : aws_iam_role.backend_task.arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }
  container_definitions = jsonencode([{
    name        = each.key
    image       = each.key == "frontend" ? var.frontend_image : var.backend_image
    essential   = true
    command     = each.value
    environment = each.key == "frontend" ? [] : local.backend_environment
    secrets     = each.key == "frontend" ? [] : local.backend_secrets
    portMappings = contains(["backend", "frontend"], each.key) ? [
      { containerPort = each.key == "backend" ? 8000 : 80, protocol = "tcp" }
    ] : []
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = each.key == "frontend" ? aws_cloudwatch_log_group.frontend.name : aws_cloudwatch_log_group.backend.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = each.key
      }
    }
  }])
  depends_on = [aws_secretsmanager_secret_version.database, aws_secretsmanager_secret_version.jwt]
}

resource "aws_ecs_service" "application" {
  for_each         = toset(["backend", "frontend"])
  name             = "${local.name}-${each.key}"
  cluster          = aws_ecs_cluster.main.id
  task_definition  = aws_ecs_task_definition.tasks[each.key].arn
  launch_type      = "FARGATE"
  platform_version = "1.4.0"
  # Provision idle services first; release scripts start them after bootstrap.
  desired_count                      = 0
  health_check_grace_period_seconds  = 60
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = true
  }
  load_balancer {
    target_group_arn = each.key == "backend" ? aws_lb_target_group.backend.arn : aws_lb_target_group.frontend.arn
    container_name   = each.key
    container_port   = each.key == "backend" ? 8000 : 80
  }
  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }
  depends_on = [aws_lb_listener_rule.api, aws_lb_listener_rule.frontend, aws_iam_role_policy.ecs_secrets, aws_iam_role_policy_attachment.ecs_execution]
}

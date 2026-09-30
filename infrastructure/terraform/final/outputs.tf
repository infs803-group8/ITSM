output "alb_dns_name" { value = aws_lb.main.dns_name }
output "cloudfront_domain_name" { value = aws_cloudfront_distribution.main.domain_name }
output "backend_repository_url" { value = aws_ecr_repository.backend.repository_url }
output "frontend_repository_url" { value = aws_ecr_repository.backend.repository_url }
output "attachment_bucket_name" { value = data.aws_s3_bucket.attachments.bucket }

output "deployment_config" {
  description = "Save with terraform output -json deployment_config; contains resource IDs, not secrets."
  value = {
    account_id                 = data.aws_caller_identity.current.account_id
    region                     = var.aws_region
    cluster                    = aws_ecs_cluster.main.arn
    base_url                   = "https://${aws_cloudfront_distribution.main.domain_name}"
    cloudfront_distribution_id = aws_cloudfront_distribution.main.id
    services = {
      for component in ["backend", "frontend"] : component => {
        name       = aws_ecs_service.application[component].name
        family     = aws_ecs_task_definition.tasks[component].family
        repository = aws_ecr_repository.backend.repository_url
      }
    }
    jobs = merge({
      database-bootstrap = {
        family    = aws_ecs_task_definition.tasks["database-bootstrap"].family
        container = "database-bootstrap"
      }
      }, {
      for job in keys(local.schedules) : job => {
        family    = aws_ecs_task_definition.tasks[job].family
        container = job
        schedule  = aws_scheduler_schedule.jobs[job].name
      }
    })
    job_network = {
      awsvpcConfiguration = {
        subnets        = aws_subnet.public[*].id
        securityGroups = [aws_security_group.jobs.id]
        assignPublicIp = "ENABLED"
      }
    }
  }
}

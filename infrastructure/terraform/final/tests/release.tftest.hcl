mock_provider "aws" {
  mock_data "aws_availability_zones" {
    defaults = { names = ["ap-southeast-2a", "ap-southeast-2b"] }
  }
  mock_data "aws_s3_bucket" {
    defaults = { bucket = "infs803-group8-dev-attachments-256329410824" }
  }
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/test" }
  }
  mock_resource "aws_lb" {
    defaults = { arn = "arn:aws:elasticloadbalancing:ap-southeast-2:123456789012:loadbalancer/app/test/1234567890123456" }
  }
  mock_resource "aws_lb_listener" {
    defaults = { arn = "arn:aws:elasticloadbalancing:ap-southeast-2:123456789012:listener/app/test/1234567890123456/1234567890123456" }
  }
  mock_resource "aws_lb_target_group" {
    defaults = { arn = "arn:aws:elasticloadbalancing:ap-southeast-2:123456789012:targetgroup/test/1234567890123456" }
  }
  mock_resource "aws_ecs_cluster" {
    defaults = {
      arn = "arn:aws:ecs:ap-southeast-2:123456789012:cluster/test"
      id  = "arn:aws:ecs:ap-southeast-2:123456789012:cluster/test"
    }
  }
  mock_resource "aws_ecs_task_definition" {
    defaults = {
      arn                  = "arn:aws:ecs:ap-southeast-2:123456789012:task-definition/test:1"
      arn_without_revision = "arn:aws:ecs:ap-southeast-2:123456789012:task-definition/test"
    }
  }
}
mock_provider "random" {}

variables {
  backend_image  = "123456789012.dkr.ecr.ap-southeast-2.amazonaws.com/backend:initial"
  frontend_image = "123456789012.dkr.ecr.ap-southeast-2.amazonaws.com/frontend:initial"
  budget_email   = "review@example.com"
}

run "release_configuration" {
  command = apply
  assert {
    condition     = alltrue([for service in aws_ecs_service.application : service.desired_count == 0])
    error_message = "Services must remain idle until the manual release script runs."
  }
  assert {
    condition     = alltrue([for schedule in aws_scheduler_schedule.jobs : schedule.state == "DISABLED"])
    error_message = "Background jobs must not start before integration approval."
  }
  assert {
    condition     = length(jsondecode(aws_ecs_task_definition.tasks["backend"].container_definitions)[0].secrets) == 2
    error_message = "Backend must receive DB/JWT secrets through ECS injection."
  }
  assert {
    condition     = length(jsondecode(aws_ecs_task_definition.tasks["frontend"].container_definitions)[0].secrets) == 0
    error_message = "Frontend must not receive backend secrets."
  }
  assert {
    condition     = aws_scheduler_schedule.jobs["attachment-cleanup"].schedule_expression == "rate(30 minutes)"
    error_message = "Attachment cleanup cadence must match the baseline."
  }
  assert {
    condition     = output.attachment_bucket_name == var.attachment_bucket_name
    error_message = "Final deployment must reuse the shared attachment bucket."
  }
}

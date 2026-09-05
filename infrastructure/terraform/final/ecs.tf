resource "aws_ecs_cluster" "main" {
  name = local.name
}

# tasks.tf creates idle services and complete task definitions. The release
# workflow updates their immutable image revisions after database bootstrap.

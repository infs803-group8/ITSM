resource "aws_ecs_cluster" "main" {
  name = local.name
}

# Separate frontend/backend Fargate task definitions and services are registered
# by the controlled deployment workflow. Set desired count to zero outside test
# and demonstration windows to limit cost.

{
  "family": "infs803-itsm-frontend",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "executionRoleArn": "${EXECUTION_ROLE_ARN}",
  "containerDefinitions": [{
    "name": "frontend",
    "image": "${FRONTEND_IMAGE}",
    "essential": true,
    "portMappings": [{"containerPort": 80, "protocol": "tcp"}]
  }]
}

{
  "family": "infs803-itsm-backend",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "executionRoleArn": "${EXECUTION_ROLE_ARN}",
  "containerDefinitions": [{
    "name": "backend",
    "image": "${BACKEND_IMAGE}",
    "essential": true,
    "portMappings": [{"containerPort": 8000, "protocol": "tcp"}],
    "environment": [
      {"name": "AWS_REGION", "value": "${AWS_REGION}"},
      {"name": "S3_BUCKET_NAME", "value": "${S3_BUCKET_NAME}"}
    ]
  }]
}

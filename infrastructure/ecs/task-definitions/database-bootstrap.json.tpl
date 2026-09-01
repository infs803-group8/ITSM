{
  "family": "infs803-itsm-database-bootstrap",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "executionRoleArn": "${EXECUTION_ROLE_ARN}",
  "containerDefinitions": [{
    "name": "database-bootstrap",
    "image": "${BACKEND_IMAGE}",
    "essential": true,
    "command": ["python", "-m", "app.db.bootstrap"]
  }]
}

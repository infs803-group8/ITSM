{
  "family": "infs803-itsm-sla-monitor",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "executionRoleArn": "${EXECUTION_ROLE_ARN}",
  "containerDefinitions": [{
    "name": "sla-monitor",
    "image": "${BACKEND_IMAGE}",
    "essential": true,
    "command": ["python", "-m", "app.domains.sla.monitor_job"]
  }]
}

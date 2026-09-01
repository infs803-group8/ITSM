# AWS architecture

CloudFront is the public HTTPS entry point. The ALB accepts CloudFront origin
traffic and routes `/api/*` to an independent backend Fargate service and other
paths to an independent frontend Fargate service. RDS is in private database
subnets; S3 stores attachments; ECR stores immutable images; CloudWatch stores
logs.

"""Configured boto3 S3 client."""

import boto3

from app.core.config import get_settings


def get_s3_client():
    settings = get_settings()
    return boto3.client("s3", region_name=settings.aws_region)

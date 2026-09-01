"""Environment-based settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "IT Service Desk API"
    app_version: str = "0.1.0"
    environment: str = "local"
    api_prefix: str = "/api/v1"
    database_url: str = "mysql+pymysql://itsm_app:local_only_password@localhost:3306/service_desk"
    cors_origins: str = "http://localhost:5173"
    aws_region: str = "ap-southeast-2"
    s3_bucket_name: str = ""
    jwt_secret: str = "replace-this-in-local-env"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()

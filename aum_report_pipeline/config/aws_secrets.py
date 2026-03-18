import json
import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv
import os


logger = logging.getLogger(__name__)


@dataclass
class SecretsConfig:
    """Container for all credentials and configuration retrieved from AWS Secrets Manager."""

    postgres_host: str
    postgres_db: str
    postgres_user: str
    postgres_password: str
    aws_access_key: Optional[str]
    aws_secret_key: Optional[str]
    s3_bucket_name: str


def _get_boto3_session_from_env() -> boto3.Session:
    """
    Create a boto3 session using either explicit environment variables or
    the default credential chain (e.g., IAM role, shared credentials file).
    """
    load_dotenv()

    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    if not region:
        raise RuntimeError("AWS region is not set. Please define AWS_REGION or AWS_DEFAULT_REGION.")

    # Prefer explicit access keys from environment for local development,
    # otherwise fall back to the standard AWS credential resolution chain.
    access_key = os.getenv("AWS_ACCESS_KEY_ID") or os.getenv("AWS_ACCESS_KEY")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY") or os.getenv("AWS_SECRET_KEY")
    session_kwargs: Dict[str, Any] = {"region_name": region}

    if access_key and secret_key:
        logger.info(
            "Creating boto3 session with explicit AWS access keys from environment",
            extra={"aws_region": region},
        )
        session_kwargs.update(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
    else:
        logger.info(
            "Creating boto3 session using default AWS credential chain",
            extra={"aws_region": region},
        )

    return boto3.Session(**session_kwargs)


def get_secrets(secret_name: str) -> SecretsConfig:
    """
    Retrieve application secrets from AWS Secrets Manager.
    Supports either the aum-report-secrets schema OR the callanOSbilling2 schema!

    :param secret_name: Name of the secret in AWS Secrets Manager.
    :return: SecretsConfig instance with all required values.
    """
    session = _get_boto3_session_from_env()
    client = session.client("secretsmanager")

    logger.info(
        "Retrieving secrets from AWS Secrets Manager",
        extra={"secret_name": secret_name},
    )
    try:
        response = client.get_secret_value(SecretId=secret_name)
    except (ClientError, BotoCoreError) as exc:
        logger.exception("Failed to retrieve secrets from AWS Secrets Manager")
        raise RuntimeError("Failed to retrieve secrets from AWS Secrets Manager") from exc

    secret_string = response.get("SecretString")
    if not secret_string:
        raise RuntimeError("SecretString is empty in AWS Secrets Manager response")

    try:
        data: Dict[str, Any] = json.loads(secret_string)
    except json.JSONDecodeError as exc:
        logger.exception("Failed to parse secret JSON")
        raise RuntimeError("Failed to parse secret JSON") from exc

    # Parse dynamically supporting both conventions
    host = data.get("postgres_host") or data.get("host") or data.get("dbHost")
    db = data.get("postgres_db") or data.get("database") or data.get("dbName")
    user = data.get("postgres_user") or data.get("username") or data.get("dbUsername")
    password = data.get("postgres_password") or data.get("password") or data.get("dbPassword")
    
    # Check what is missing
    missing = []
    if not host: missing.append("host")
    if not db: missing.append("database")
    if not user: missing.append("username")
    if not password: missing.append("password")

    if missing:
        logger.error("Missing required keys in secret", extra={"missing_keys": missing})
        raise RuntimeError(f"Missing required DB keys in secret '{secret_name}': {', '.join(missing)}")

    # The original team secret 'callanOSbilling2' does NOT contain 's3_bucket_name'.
    # We must retrieve it from the environment variable set on Lambda.
    s3_bucket = os.getenv("S3_BUCKET_NAME") or data.get("s3_bucket_name")
    if not s3_bucket:
         raise RuntimeError("S3_BUCKET_NAME is not set in environment or secret!")

    logger.info(f"Successfully retrieved secrets for '{secret_name}'")

    return SecretsConfig(
        postgres_host=host,
        postgres_db=db,
        postgres_user=user,
        postgres_password=password,
        aws_access_key=data.get("aws_access_key"),
        aws_secret_key=data.get("aws_secret_key"),
        s3_bucket_name=s3_bucket,
    )

__all__ = ["SecretsConfig", "get_secrets"]

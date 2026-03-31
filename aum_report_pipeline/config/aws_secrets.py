import json
import logging
import time
from dataclasses import dataclass
from typing import Dict, Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError
import os

try:
    # Optional: for local development only. In Lambda you typically don't need it.
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover
    load_dotenv = None


logger = logging.getLogger(__name__)
DEFAULT_S3_BUCKET_NAME = "aris-data-extracts"


@dataclass
class SecretsConfig:
    """Container for all credentials and configuration retrieved from AWS Secrets Manager."""

    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str
    s3_bucket_name: str


def _get_boto3_session_from_env() -> boto3.Session:
    """
    Create a boto3 session using either explicit environment variables or
    the default credential chain (e.g., IAM role, shared credentials file).
    """
    if load_dotenv is not None:
        load_dotenv()

    # Lambda normally provides AWS_REGION/AWS_DEFAULT_REGION automatically, but
    # defaulting keeps this app runnable with "no env vars" for region.
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"

    session_kwargs: Dict[str, Any] = {"region_name": region}
    # Let boto3 resolve credentials from the default credential chain:
    # - Lambda execution role (Lambda)
    # - Env vars / shared credentials file (local dev)
    logger.info("Creating boto3 session using default AWS credential chain", extra={"aws_region": region})

    return boto3.Session(**session_kwargs)


def get_secrets(secret_name: str) -> SecretsConfig:
    """
    Retrieve application secrets from AWS Secrets Manager.

    The secret is expected to be a JSON object with at least:
        host, port, database, username, password

    :param secret_name: Name of the secret in AWS Secrets Manager.
    :return: SecretsConfig instance with all required values.
    :raises RuntimeError: If secrets cannot be retrieved or parsed.
    """
    started = time.perf_counter()
    session = _get_boto3_session_from_env()
    client = session.client("secretsmanager")
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"

    logger.info(
        "SECRETS_FETCH_START",
        extra={"secret_name": secret_name, "region": region, "service": "secretsmanager"},
    )
    try:
        response = client.get_secret_value(SecretId=secret_name)
    except (ClientError, BotoCoreError) as exc:
        logger.exception(
            "SECRETS_FETCH_FAILED",
            extra={
                "secret_name": secret_name,
                "region": region,
                "error_type": type(exc).__name__,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
            },
        )
        raise RuntimeError("Failed to retrieve secrets from AWS Secrets Manager") from exc

    secret_string = response.get("SecretString")
    if not secret_string:
        raise RuntimeError("SecretString is empty in AWS Secrets Manager response")

    try:
        data: Dict[str, Any] = json.loads(secret_string)
    except json.JSONDecodeError as exc:
        logger.exception("Failed to parse secret JSON")
        raise RuntimeError("Failed to parse secret JSON") from exc

    # Secrets Manager value keys in your screenshot:
    # - username, password, engine, host, port, database, ...
    # Map them to the internal SecretsConfig fields.
    required_keys = ["host", "port", "database", "username", "password"]
    missing = [k for k in required_keys if k not in data or data[k] in (None, "")]
    if missing:
        logger.error("Missing required keys in secret", extra={"missing_keys": missing})
        raise RuntimeError(f"Missing required keys in secret: {', '.join(missing)}")

    # Bucket name is hardcoded as fallback because this secret may not be editable.
    s3_bucket_name = data.get("s3_bucket_name") or DEFAULT_S3_BUCKET_NAME

    logger.info(
        "SECRETS_FETCH_SUCCESS",
        extra={
            "secret_name": secret_name,
            "region": region,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "db_host": data["host"],
            "db_port": data["port"],
            "db_name": data["database"],
            "s3_bucket": s3_bucket_name,
        },
    )

    return SecretsConfig(
        postgres_host=data["host"],
        postgres_port=int(data["port"]),
        postgres_db=data["database"],
        postgres_user=data["username"],
        postgres_password=data["password"],
        s3_bucket_name=s3_bucket_name,
    )


__all__ = ["SecretsConfig", "get_secrets"]


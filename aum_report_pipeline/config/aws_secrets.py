import json
import logging
from dataclasses import dataclass
from typing import Dict, Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError
import os


logger = logging.getLogger(__name__)


@dataclass
class SecretsConfig:
    """Container for all credentials and configuration retrieved from AWS Secrets Manager."""

    postgres_host: str
    postgres_db: str
    postgres_user: str
    postgres_password: str
    s3_bucket_name: str


def get_secrets(secret_name: str) -> SecretsConfig:
    """
    Retrieve application secrets from AWS Secrets Manager.
    Supports both the 'aum-report-secrets' schema and the 'callanOSbilling2' schema.

    :param secret_name: Name of the secret in AWS Secrets Manager.
    :return: SecretsConfig instance with all required values.
    """
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    if not region:
        raise RuntimeError("AWS region is not set. Please define AWS_REGION or AWS_DEFAULT_REGION.")

    # Create the boto3 client purely using the region, AWS IAM Role will handle credentials automatically
    client = boto3.client("secretsmanager", region_name=region)

    logger.info(f"Retrieving secret '{secret_name}' from AWS Secrets Manager in {region}...")

    try:
        response = client.get_secret_value(SecretId=secret_name)
    except ClientError as exc:
        # Surface the EXACT AWS error code in the logs so it shows in CloudWatch
        error_code = exc.response["Error"]["Code"]
        error_msg = exc.response["Error"]["Message"]
        logger.error(
            f"AWS ClientError fetching secret '{secret_name}': "
            f"[{error_code}] {error_msg}"
        )
        raise RuntimeError(
            f"Failed to retrieve secret '{secret_name}' from Secrets Manager. "
            f"AWS Error: [{error_code}] {error_msg}"
        ) from exc
    except BotoCoreError as exc:
        logger.exception(f"BotoCoreError fetching secret '{secret_name}': {exc}")
        raise RuntimeError(
            f"Failed to retrieve secret '{secret_name}' from Secrets Manager: {exc}"
        ) from exc

    secret_string = response.get("SecretString")
    if not secret_string:
        raise RuntimeError("SecretString is empty in AWS Secrets Manager response")

    try:
        data: Dict[str, Any] = json.loads(secret_string)
    except json.JSONDecodeError as exc:
        logger.exception("Failed to parse secret JSON")
        raise RuntimeError("Failed to parse secret JSON") from exc

    # Parse dynamically — supports both 'aum-report-secrets' and 'callanOSbilling2' schemas
    host = data.get("postgres_host") or data.get("host") or data.get("dbHost")
    db = data.get("postgres_db") or data.get("database") or data.get("dbName")
    user = data.get("postgres_user") or data.get("username") or data.get("dbUsername")
    password = data.get("postgres_password") or data.get("password") or data.get("dbPassword")

    missing = []
    if not host:     missing.append("host")
    if not db:       missing.append("database")
    if not user:     missing.append("username")
    if not password: missing.append("password")

    if missing:
        logger.error(f"Missing required DB keys in secret '{secret_name}': {missing}")
        raise RuntimeError(
            f"Missing required DB keys in secret '{secret_name}': {', '.join(missing)}"
        )

    # S3 bucket: prefer env var, fall back to value inside the secret
    s3_bucket = os.getenv("S3_BUCKET_NAME") or data.get("s3_bucket_name")
    if not s3_bucket:
        raise RuntimeError(
            "S3_BUCKET_NAME is not set. Add it as a Lambda environment variable."
        )

    logger.info(f"Successfully retrieved secret '{secret_name}'. Host={host}, DB={db}")

    return SecretsConfig(
        postgres_host=host,
        postgres_db=db,
        postgres_user=user,
        postgres_password=password,
        s3_bucket_name=s3_bucket,
    )


__all__ = ["SecretsConfig", "get_secrets"]

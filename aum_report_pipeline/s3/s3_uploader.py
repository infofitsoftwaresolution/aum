import logging
from pathlib import Path
from typing import Iterable, Tuple

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from aum_report_pipeline.config.aws_secrets import SecretsConfig


logger = logging.getLogger(__name__)


def _create_s3_client(secrets: SecretsConfig, region: str | None = None):
    """
    Create an S3 client using credentials from Secrets Manager if present,
    otherwise rely on the default boto3 credential chain.
    """
    session_kwargs = {}
    if region:
        session_kwargs["region_name"] = region

    if secrets.aws_access_key and secrets.aws_secret_key:
        logger.info("Creating S3 client with access key from Secrets Manager")
        session = boto3.Session(
            aws_access_key_id=secrets.aws_access_key,
            aws_secret_access_key=secrets.aws_secret_key,
            **session_kwargs,
        )
    else:
        logger.info("Creating S3 client using default AWS credentials")
        session = boto3.Session(**session_kwargs)

    return session.client("s3")


def upload_reports_to_s3(
    generated_files: Iterable[Tuple[str, Path]],
    secrets: SecretsConfig,
    s3_prefix_root: str = "managers/",
    region: str | None = None,
) -> None:
    """
    Upload generated report files to S3 using the required folder structure.

    S3 layout:
        s3://<bucket>/<s3_prefix_root>/<ManagerName>/<file.xlsx>

    :param generated_files: Iterable of (manager_firm, local_path) tuples.
    :param secrets: SecretsConfig with S3 bucket name and AWS credentials.
    :param s3_prefix_root: Root prefix in the bucket (default 'managers/').
    :param region: Optional AWS region override for S3 client.
    """
    client = _create_s3_client(secrets, region=region)

    bucket = secrets.s3_bucket_name
    logger.info(
        "Uploading reports to S3",
        extra={"bucket": bucket, "prefix_root": s3_prefix_root},
    )

    for manager_firm, local_path in generated_files:
        safe_manager = local_path.parent.name  # Already sanitized in report generation.
        key = f"{s3_prefix_root.rstrip('/')}/{safe_manager}/{local_path.name}"

        logger.info(
            "Uploading file to S3",
            extra={
                "bucket": bucket,
                "key": key,
                "local_path": str(local_path),
                "manager_firm": manager_firm,
            },
        )

        try:
            client.upload_file(str(local_path), bucket, key)
        except (ClientError, BotoCoreError):  # pragma: no cover - network/service specific
            logger.exception(
                "Failed to upload file to S3",
                extra={"bucket": bucket, "key": key, "local_path": str(local_path)},
            )
            raise

    logger.info("All report files uploaded to S3 successfully")


__all__ = ["upload_reports_to_s3"]


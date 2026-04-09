import json
import logging
import os
from pathlib import Path
import stat

import boto3
import paramiko
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

secrets_client = boto3.client("secretsmanager")
s3_client = boto3.client("s3")

SECRET_NAME = "schwab_sftp"
TARGET_BUCKET = "callan-sftp"


def _read_secret() -> dict:
    try:
        response = secrets_client.get_secret_value(SecretId=SECRET_NAME)
    except (ClientError, BotoCoreError) as exc:
        raise RuntimeError(f"Failed to read secret '{SECRET_NAME}'") from exc

    secret_string = response.get("SecretString")
    if not secret_string:
        raise RuntimeError(f"Secret '{SECRET_NAME}' has empty SecretString")

    data = json.loads(secret_string)
    required = ["hostname", "port", "username", "password"]
    missing = [k for k in required if k not in data or data[k] in (None, "")]
    if missing:
        raise RuntimeError(f"Secret '{SECRET_NAME}' missing keys: {', '.join(missing)}")
    return data


def _select_remote_path(secret: dict) -> str:
    return os.getenv("SFTP_REMOTE_PATH") or secret.get("remote_path") or "."


def _select_s3_prefix() -> str:
    prefix = os.getenv("S3_PREFIX", "Schwab/").strip()
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    return prefix


def _list_zip_files(sftp: paramiko.SFTPClient, remote_path: str) -> list[str]:
    files = []
    for attr in sftp.listdir_attr(remote_path):
        filename = attr.filename
        if filename.lower().endswith(".zip"):
            files.append(filename)
    return sorted(files)


def _log_remote_listing(sftp: paramiko.SFTPClient, remote_path: str) -> None:
    entries = sftp.listdir_attr(remote_path)
    logger.info("SFTP_REMOTE_LIST_START | path=%s entry_count=%s", remote_path, len(entries))
    for entry in entries:
        entry_type = "DIR" if stat.S_ISDIR(entry.st_mode) else "FILE"
        logger.info(
            "SFTP_REMOTE_ENTRY | type=%s name=%s size_bytes=%s",
            entry_type,
            entry.filename,
            entry.st_size,
        )
    logger.info("SFTP_REMOTE_LIST_DONE | path=%s", remote_path)


def lambda_handler(event, context):
    logger.info("HANDLER_START | event=%s", json.dumps(event, default=str))
    secret = _read_secret()
    host = secret["hostname"]
    port = int(secret["port"])
    username = secret["username"]
    password = secret["password"]

    remote_path = _select_remote_path(secret)
    bucket = TARGET_BUCKET
    s3_prefix = _select_s3_prefix()

    logger.info(
        "CONFIG | host=%s port=%s remote_path=%s bucket=%s s3_prefix=%s",
        host,
        port,
        remote_path,
        bucket,
        s3_prefix,
    )

    transport = None
    sftp = None
    uploaded = 0
    attempted = 0

    try:
        transport = paramiko.Transport((host, port))
        transport.connect(username=username, password=password)
        sftp = paramiko.SFTPClient.from_transport(transport)
        logger.info("SFTP_CONNECT_OK")
        _log_remote_listing(sftp, remote_path)

        zip_files = _list_zip_files(sftp, remote_path)
        logger.info("SFTP_LIST_OK | zip_file_count=%s", len(zip_files))

        for filename in zip_files:
            attempted += 1
            remote_file = f"{remote_path.rstrip('/')}/{filename}"
            local_file = f"/tmp/{filename}"
            s3_key = f"{s3_prefix}{filename}"

            logger.info("FILE_START | remote=%s s3_key=%s", remote_file, s3_key)
            sftp.get(remote_file, local_file)
            s3_client.upload_file(local_file, bucket, s3_key)
            uploaded += 1
            logger.info("FILE_DONE | uploaded=s3://%s/%s", bucket, s3_key)

            try:
                local_path = Path(local_file)
                if local_path.exists():
                    local_path.unlink()
            except Exception:
                logger.warning("TMP_CLEANUP_FAILED | file=%s", local_file)

        logger.info("HANDLER_DONE | attempted=%s uploaded=%s", attempted, uploaded)
        return {"statusCode": 200, "attempted": attempted, "uploaded": uploaded}
    except Exception:
        logger.exception("HANDLER_FAILED")
        raise
    finally:
        if sftp is not None:
            sftp.close()
        if transport is not None:
            transport.close()

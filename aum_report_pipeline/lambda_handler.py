"""
AWS Lambda entry point for the AUM Report Pipeline.

Handler path (set this in Lambda console):
    aum_report_pipeline.lambda_handler.handler

The handler delegates all pipeline logic to run_pipeline() in main.py.
Nothing in this file contains business logic — it is purely a Lambda adapter.

Supported event payload (all fields optional):
    {
        "log_level": "DEBUG"   // override LOG_LEVEL env var for this invocation
    }

Lambda environment variables required:
    AWS_REGION          - AWS region (e.g. ap-south-1)
    AWS_SECRETS_NAME    - Name of the secret in AWS Secrets Manager

Lambda environment variables optional:
    LOG_LEVEL           - Logging level (INFO / DEBUG / WARNING, default INFO)

The function reads all other config (DB creds, S3 bucket) from Secrets Manager.
"""
import logging
import os

from aum_report_pipeline.main import run_pipeline

# Module-level logger — configured by run_pipeline() → configure_logging()
logger = logging.getLogger(__name__)


def handler(event: dict, context: object) -> dict:
    """
    AWS Lambda handler for the AUM Report Pipeline.

    Triggered by:
        - EventBridge Scheduler (monthly cron)
        - Manual invocation from AWS Console / CLI

    Args:
        event:   Dict passed by the trigger (EventBridge sends {}, manual can pass overrides).
        context: Lambda context object (contains function_name, request_id, etc.).

    Returns:
        Dict with statusCode and body for compatibility with API Gateway if needed.

    Raises:
        RuntimeError: Propagated from run_pipeline() on any pipeline failure.
                      Lambda marks the invocation as failed and triggers DLQ if configured.
    """
    # Allow per-invocation log level override via event payload
    if isinstance(event, dict) and event.get("log_level"):
        os.environ["LOG_LEVEL"] = str(event["log_level"]).upper()

    logger.info(
        "Lambda handler invoked",
        extra={
            "function_name": getattr(context, "function_name", "unknown"),
            "request_id": getattr(context, "aws_request_id", "unknown"),
            "event_keys": list(event.keys()) if isinstance(event, dict) else [],
        },
    )

    # Delegate entirely to the shared pipeline — same code that runs locally
    run_pipeline()

    logger.info("Lambda handler completed successfully")
    return {
        "statusCode": 200,
        "body": "AUM report pipeline completed successfully",
    }

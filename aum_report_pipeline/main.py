import logging
import os
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

from aum_report_pipeline.config.aws_secrets import get_secrets
from aum_report_pipeline.database.postgres_connection import run_query_to_dataframe
from aum_report_pipeline.reports.report_generator import (
    ReportDateWindow,
    generate_manager_reports,
)
from aum_report_pipeline.s3.s3_uploader import upload_reports_to_s3
from aum_report_pipeline.utils.cleanup import cleanup_output_directory


def configure_logging() -> None:
    """Configure application-wide structured logging."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def _month_end_for(date_value: date) -> date:
    """Return the month-end date for the given date."""
    next_month = (date_value.replace(day=28) + timedelta(days=4)).replace(day=1)
    return next_month - timedelta(days=1)


def compute_default_date_windows(today: date | None = None) -> list[ReportDateWindow]:
    """
    Compute two default report windows based on today's date:

        - Latest month: prior = month-end two months ago, latest = month-end last month
        - Previous month: prior = month-end three months ago, latest = month-end two months ago
    """
    if today is None:
        today = date.today()

    last_month_end = _month_end_for(today.replace(day=1) - timedelta(days=1))
    prior_month_end = _month_end_for(last_month_end.replace(day=1) - timedelta(days=1))
    two_back_end = _month_end_for(prior_month_end.replace(day=1) - timedelta(days=1))

    latest_label = f"{last_month_end.year:04d}-{last_month_end.month:02d}"
    previous_label = f"{prior_month_end.year:04d}-{prior_month_end.month:02d}"

    return [
        ReportDateWindow(
            label=latest_label,
            prior_month_end=prior_month_end,
            latest_month_end=last_month_end,
        ),
        ReportDateWindow(
            label=previous_label,
            prior_month_end=two_back_end,
            latest_month_end=prior_month_end,
        ),
    ]


def main() -> None:
    """Orchestrate the end-to-end AUM report pipeline."""
    load_dotenv()
    configure_logging()
    logger = logging.getLogger(__name__)

    logger.info("Starting AUM report pipeline")

    # Configuration from environment
    secret_name = os.getenv("AWS_SECRETS_NAME")
    if not secret_name:
        logger.error("AWS_SECRETS_NAME environment variable is required")
        raise SystemExit("AWS_SECRETS_NAME environment variable is required")

    project_root = Path(__file__).resolve().parent
    sql_path = project_root / "queries" / "aum_query.sql"
    output_root = Path(os.getenv("OUTPUT_DIR", project_root.parent / "output"))

    try:
        # 1. Retrieve secrets
        logger.info("Step 1: Retrieving secrets from AWS Secrets Manager")
        secrets = get_secrets(secret_name)

        # 2. Connect to PostgreSQL & run query
        logger.info("Step 2: Executing AUM query against PostgreSQL")
        df = run_query_to_dataframe(str(sql_path), secrets)
        if df.empty:
            logger.warning("No AUM data returned from PostgreSQL; exiting gracefully")
            return

        # 3. Generate reports per manager
        logger.info("Step 3: Generating Excel reports per manager")
        date_windows = compute_default_date_windows()
        generated_files = generate_manager_reports(df, output_root, date_windows)
        if not generated_files:
            logger.warning("No reports were generated; exiting gracefully")
            return

        # 4. Upload to S3
        logger.info("Step 4: Uploading generated reports to S3")
        aws_region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
        upload_reports_to_s3(
            generated_files,
            secrets,
            s3_prefix_root="managers/",
            region=aws_region,
        )

        # 5. Cleanup local files
        logger.info("Step 5: Cleaning up local generated files")
        cleanup_output_directory(output_root)

        logger.info("AUM report pipeline completed successfully")

    except Exception as exc:  # noqa: BLE001
        logger.exception("AUM report pipeline failed")
        raise SystemExit(f"AUM report pipeline failed: {exc}") from exc


if __name__ == "__main__":
    main()


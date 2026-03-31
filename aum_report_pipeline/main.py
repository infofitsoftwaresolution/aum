import logging
import os
import time
from datetime import date, timedelta
from pathlib import Path

try:
    # Optional dependency for local development only (no need in Lambda)
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover
    load_dotenv = None

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
    if load_dotenv is not None and not os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        # Load .env only when running locally.
        load_dotenv()
    configure_logging()
    logger = logging.getLogger(__name__)

    run_started = time.perf_counter()
    logger.info("PIPELINE_START")

    # Hardcoded defaults so Lambda execution requires no env vars.
    secret_name = "callanOSbilling2"

    project_root = Path(__file__).resolve().parent
    sql_path = project_root / "queries" / "aum_query.sql"
    # Lambda writable directory is /tmp only.
    output_root = Path("/tmp/output")

    try:
        # 1. Retrieve secrets
        step_started = time.perf_counter()
        logger.info("STEP_1_START | Retrieving secrets", extra={"secret_name": secret_name})
        secrets = get_secrets(secret_name)
        logger.info(
            "STEP_1_SUCCESS | Secrets retrieved",
            extra={
                "elapsed_seconds": round(time.perf_counter() - step_started, 3),
                "db_host": secrets.postgres_host,
                "db_port": secrets.postgres_port,
                "db_name": secrets.postgres_db,
                "s3_bucket": secrets.s3_bucket_name,
            },
        )

        # 2. Compute reporting windows (e.g. latest month and previous month)
        step_started = time.perf_counter()
        logger.info("STEP_2_START | Computing reporting windows")
        date_windows = compute_default_date_windows()
        logger.info(
            "STEP_2_SUCCESS | Reporting windows computed",
            extra={
                "elapsed_seconds": round(time.perf_counter() - step_started, 3),
                "window_count": len(date_windows),
                "windows": [w.label for w in date_windows],
            },
        )

        # 3. For each window, run the parameterised query and generate reports
        step_started = time.perf_counter()
        logger.info("STEP_3_START | Executing AUM queries and generating Excel reports")
        all_generated_files: list[tuple[str, Path]] = []

        for window in date_windows:
            window_started = time.perf_counter()
            logger.info(
                "STEP_3_WINDOW_START | Running AUM query for reporting window",
                extra={
                    "label": window.label,
                    "prior_month_end": window.prior_month_end.isoformat(),
                    "latest_month_end": window.latest_month_end.isoformat(),
                },
            )

            # Use latest_month_end as the anchor month for the SQL logic.
            df_window = run_query_to_dataframe(
                str(sql_path),
                secrets,
                params={"anchor_month": window.latest_month_end},
            )
            if df_window.empty:
                logger.warning(
                    "STEP_3_WINDOW_EMPTY | AUM query returned no rows; skipping report generation",
                    extra={"label": window.label},
                )
                continue

            generated_for_window = generate_manager_reports(df_window, output_root, [window])
            all_generated_files.extend(generated_for_window)
            logger.info(
                "STEP_3_WINDOW_SUCCESS | Reports generated for window",
                extra={
                    "label": window.label,
                    "row_count": len(df_window),
                    "generated_files": len(generated_for_window),
                    "elapsed_seconds": round(time.perf_counter() - window_started, 3),
                },
            )

        if not all_generated_files:
            logger.warning("STEP_3_NO_FILES | No reports were generated for any window; exiting gracefully")
            return
        logger.info(
            "STEP_3_SUCCESS | Query and report generation completed",
            extra={
                "elapsed_seconds": round(time.perf_counter() - step_started, 3),
                "total_generated_files": len(all_generated_files),
            },
        )

        # 4. Upload to S3
        step_started = time.perf_counter()
        aws_region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"
        logger.info(
            "STEP_4_START | Uploading generated reports to S3",
            extra={
                "aws_region": aws_region,
                "file_count": len(all_generated_files),
                "bucket": secrets.s3_bucket_name,
            },
        )
        upload_reports_to_s3(
            all_generated_files,
            secrets,
            s3_prefix_root="managers/",
            region=aws_region,
        )
        logger.info(
            "STEP_4_SUCCESS | Upload completed",
            extra={"elapsed_seconds": round(time.perf_counter() - step_started, 3)},
        )

        # 5. Cleanup local files
        step_started = time.perf_counter()
        logger.info("STEP_5_START | Cleaning up local generated files", extra={"output_root": str(output_root)})
        cleanup_output_directory(output_root)
        logger.info(
            "STEP_5_SUCCESS | Cleanup completed",
            extra={"elapsed_seconds": round(time.perf_counter() - step_started, 3)},
        )

        logger.info(
            "PIPELINE_SUCCESS",
            extra={"total_elapsed_seconds": round(time.perf_counter() - run_started, 3)},
        )

    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "PIPELINE_FAILED",
            extra={"failed_after_seconds": round(time.perf_counter() - run_started, 3)},
        )
        raise SystemExit(f"AUM report pipeline failed: {exc}") from exc


if __name__ == "__main__":
    main()


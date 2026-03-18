import logging
import os
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

from aum_report_pipeline.config.aws_secrets import get_secrets, SecretsConfig
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


def _run_demo_pipeline(output_root: Path, logger: logging.Logger) -> None:
    """
    Demo pipeline path — uses synthetic sample data instead of PostgreSQL.

    Triggered when DEMO_MODE=true is set as an environment variable.

    Requirements (env vars):
        S3_BUCKET_NAME  - S3 bucket to upload demo reports to
        AWS_REGION      - AWS region for S3 client

    Skipped entirely in demo mode:
        - AWS Secrets Manager (no secret_name needed)
        - PostgreSQL / psycopg2 (no DB connection)

    Everything else runs identically to production:
        - Date window computation
        - Per-manager Excel report generation
        - S3 upload under  managers/<ManagerName>/
        - Local /tmp cleanup
    """
    # Import demo data only when actually needed — never loaded in production
    from aum_report_pipeline.demo.sample_data import generate_sample_dataframe  # noqa: PLC0415

    logger.info("=" * 60)
    logger.info("DEMO MODE ENABLED")
    logger.info("  - PostgreSQL: SKIPPED (using synthetic sample data)")
    logger.info("  - Secrets Manager: SKIPPED (using env vars for S3)")
    logger.info("=" * 60)

    # Read S3 bucket from env var directly — no Secrets Manager needed
    s3_bucket = os.getenv("S3_BUCKET_NAME")
    if not s3_bucket:
        raise RuntimeError(
            "S3_BUCKET_NAME environment variable is required when DEMO_MODE=true. "
            "Set it to the name of your S3 bucket (e.g. my-aum-demo-bucket)."
        )

    # Build a minimal SecretsConfig for demo — only s3_bucket_name is used.
    # DB fields are empty strings — they are never used in demo mode.
    demo_secrets = SecretsConfig(
        postgres_host="",
        postgres_port="5432",
        postgres_db="",
        postgres_user="",
        postgres_password="",
        s3_bucket_name=s3_bucket,
    )

    # Step D1: Compute reporting windows (same as production)
    logger.info("Demo Step 1: Computing reporting windows")
    date_windows = compute_default_date_windows()

    # Step D2: Generate sample data for each window
    logger.info("Demo Step 2: Generating sample data and Excel reports")
    all_generated_files: list[tuple[str, Path]] = []

    for window in date_windows:
        logger.info(
            "Demo: Generating reports for window",
            extra={
                "label": window.label,
                "prior_month_end": window.prior_month_end.isoformat(),
                "latest_month_end": window.latest_month_end.isoformat(),
            },
        )
        # Use synthetic DataFrame — same schema as aum_query.sql output
        df_window = generate_sample_dataframe()

        if df_window.empty:
            logger.warning("Demo sample data returned empty DataFrame — skipping window")
            continue

        generated = generate_manager_reports(
            df=df_window,
            output_dir=output_root / window.label,
            report_month=window.latest_month_end,
        )
        all_generated_files.extend(generated)

    if not all_generated_files:
        logger.warning("No demo reports generated")
        return

    # Step D3: Upload to S3
    logger.info("Demo Step 3: Uploading demo reports to S3")
    aws_region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    
    upload_reports_to_s3(
        generated_files=all_generated_files,
        secrets=demo_secrets,
        region=aws_region,
    )

    # Step D4: Cleanup (identical to production)
    logger.info("Demo Step 4: Cleaning up local demo files")
    cleanup_output_directory(output_root)

    logger.info("DEMO MODE: AUM report pipeline completed successfully")


def run_pipeline() -> None:
    """
    Core pipeline logic — shared between local execution and AWS Lambda.

    This function does NOT call load_dotenv() so it is safe to call from Lambda
    (where there is no .env file). Call main() for local execution which loads
    dotenv first.

    Modes:
        DEMO_MODE=true   → Uses synthetic sample data. No PostgreSQL, no Secrets Manager.
                           Requires only: S3_BUCKET_NAME, AWS_REGION env vars.
        DEMO_MODE=false  → Full production pipeline. Requires: AWS_SECRETS_NAME, AWS_REGION.

    Output directory resolution:
        - On AWS Lambda  →  /tmp/aum_output  (only writable path on Lambda)
        - Locally        →  OUTPUT_DIR env var, or <project_root>/../output

    Raises:
        RuntimeError: If required env vars are missing or any pipeline step fails.
    """
    configure_logging()
    logger = logging.getLogger(__name__)

    logger.info("Starting AUM report pipeline")

    project_root = Path(__file__).resolve().parent

    # On AWS Lambda the only writable path is /tmp.
    # AWS_LAMBDA_FUNCTION_NAME is always injected by the Lambda runtime,
    # so we use its presence to detect we are running inside Lambda.
    if os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        output_root = Path("/tmp/aum_output")
        logger.info(
            "Running inside AWS Lambda — output directory set to /tmp/aum_output"
        )
    else:
        output_root = Path(os.getenv("OUTPUT_DIR", str(project_root.parent / "output")))

    # ------------------------------------------------------------------
    # Check if DEMO_MODE is enabled
    # ------------------------------------------------------------------
    demo_mode = os.getenv("DEMO_MODE", "false").strip().lower() in ("true", "1", "yes")

    if demo_mode:
        try:
            _run_demo_pipeline(output_root, logger)
        except Exception as exc:  # noqa: BLE001
            logger.exception("AUM report pipeline failed in DEMO MODE")
            raise RuntimeError(f"AUM report pipeline (DEMO) failed: {exc}") from exc
        return

    # ------------------------------------------------------------------
    # PRODUCTION MODE — full PostgreSQL + Secrets Manager pipeline
    # ------------------------------------------------------------------
    secret_name = os.getenv("AWS_SECRETS_NAME")
    if not secret_name:
        logger.error("AWS_SECRETS_NAME environment variable is required")
        raise RuntimeError("AWS_SECRETS_NAME environment variable is required")

    sql_path = project_root / "queries" / "aum_query.sql"

    try:
        # 1. Retrieve secrets
        logger.info("Step 1: Retrieving secrets from AWS Secrets Manager")
        secrets = get_secrets(secret_name)

        # 2. Compute reporting windows (e.g. latest month and previous month)
        logger.info("Step 2: Computing reporting windows")
        date_windows = compute_default_date_windows()

        # 3. For each window, run the parameterised query and generate reports
        logger.info("Step 3: Executing AUM queries and generating Excel reports")
        all_generated_files: list[tuple[str, Path]] = []

        for window in date_windows:
            logger.info(
                "Running AUM query for reporting window",
                extra={
                    "label": window.label,
                    "prior_month_end": window.prior_month_end.isoformat(),
                    "latest_month_end": window.latest_month_end.isoformat(),
                },
            )

            # Pass parameters expected by the aum_query.sql explicitly mapping parameters.
            df_window = run_query_to_dataframe(
                sql_path=str(sql_path),
                secrets=secrets,
                params={"anchor_month": window.latest_month_end},
            )

            if df_window.empty:
                logger.warning(
                    f"No data returned for window {window.label} — skipping"
                )
                continue

            generated = generate_manager_reports(
                df=df_window,
                output_dir=output_root / window.label,
                report_month=window.latest_month_end,
            )
            all_generated_files.extend(generated)

        if not all_generated_files:
            logger.warning("No reports generated for any window")
            return

        # 4. Upload to S3
        logger.info("Step 4: Uploading generated reports to S3")
        aws_region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
        upload_reports_to_s3(
            generated_files=all_generated_files,
            secrets=secrets,
            region=aws_region,
        )

        # 5. Cleanup
        logger.info("Step 5: Cleaning up local output directory")
        cleanup_output_directory(output_root)

        logger.info("AUM report pipeline completed successfully")

    except Exception as exc:  # noqa: BLE001
        logger.exception("AUM report pipeline failed")
        raise RuntimeError(f"AUM report pipeline failed: {exc}") from exc


def main() -> None:
    """Local execution entrypoint."""
    load_dotenv()
    # Explicit check for local dev to guide user away from reserved Lambda var
    if not os.getenv("AWS_DEFAULT_REGION") and not os.getenv("AWS_REGION"):
        # We fallback to defaulting for local if nothing set, though pipeline requires it
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    run_pipeline()


if __name__ == "__main__":
    main()

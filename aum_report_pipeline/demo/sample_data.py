"""
Demo sample data generator for the AUM Report Pipeline.

This module is ONLY imported when DEMO_MODE=true is set as an environment variable.
It generates a realistic pandas DataFrame that exactly mimics the schema returned
by aum_query.sql so that the rest of the pipeline (report generation, S3 upload,
cleanup) runs identically to a real production run.

Schema matches aum_query.sql output:
    manager_firm      (str)   - manager firm name
    model_name        (str)   - investment model name
    aum_latest_month  (float) - AUM value at the latest month-end date
    aum_prior_month   (float) - AUM value at the prior month-end date
"""

import logging

import pandas as pd


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Realistic sample AUM data — 5 managers, 2 models each = 10 rows
# Values are in USD. Numbers are representative of a mid-size RIA.
# ---------------------------------------------------------------------------
_SAMPLE_RECORDS = [
    {
        "manager_firm": "Apex Capital Management",
        "model_name": "Apex Growth Model",
        "aum_latest_month": 142_500_000.00,
        "aum_prior_month": 138_200_000.00,
    },
    {
        "manager_firm": "Apex Capital Management",
        "model_name": "Apex Value Model",
        "aum_latest_month": 87_300_000.00,
        "aum_prior_month": 84_100_000.00,
    },
    {
        "manager_firm": "BlueStar Investment Partners",
        "model_name": "BlueStar Core Equity",
        "aum_latest_month": 215_700_000.00,
        "aum_prior_month": 209_400_000.00,
    },
    {
        "manager_firm": "BlueStar Investment Partners",
        "model_name": "BlueStar Fixed Income",
        "aum_latest_month": 98_400_000.00,
        "aum_prior_month": 101_200_000.00,
    },
    {
        "manager_firm": "Meridian Asset Advisors",
        "model_name": "Meridian Balanced Portfolio",
        "aum_latest_month": 63_150_000.00,
        "aum_prior_month": 61_800_000.00,
    },
    {
        "manager_firm": "Meridian Asset Advisors",
        "model_name": "Meridian International Growth",
        "aum_latest_month": 44_900_000.00,
        "aum_prior_month": 43_700_000.00,
    },
    {
        "manager_firm": "Summit Wealth Strategies",
        "model_name": "Summit Aggressive Growth",
        "aum_latest_month": 178_600_000.00,
        "aum_prior_month": 172_300_000.00,
    },
    {
        "manager_firm": "Summit Wealth Strategies",
        "model_name": "Summit Conservative Income",
        "aum_latest_month": 129_800_000.00,
        "aum_prior_month": 131_500_000.00,
    },
    {
        "manager_firm": "Pinnacle Global Funds",
        "model_name": "Pinnacle ESG Model",
        "aum_latest_month": 56_200_000.00,
        "aum_prior_month": 52_900_000.00,
    },
    {
        "manager_firm": "Pinnacle Global Funds",
        "model_name": "Pinnacle Emerging Markets",
        "aum_latest_month": 34_750_000.00,
        "aum_prior_month": 33_100_000.00,
    },
]


def generate_sample_dataframe() -> pd.DataFrame:
    """
    Return a DataFrame that exactly mimics the output of aum_query.sql.

    This is used in DEMO_MODE to bypass the PostgreSQL database without
    changing any downstream pipeline code (report generation, S3 upload,
    cleanup all run identically).

    Returns:
        pd.DataFrame with columns:
            manager_firm, model_name, aum_latest_month, aum_prior_month
    """
    logger.info(
        "DEMO MODE: Generating synthetic AUM sample data (no database required)",
        extra={"record_count": len(_SAMPLE_RECORDS)},
    )

    df = pd.DataFrame(_SAMPLE_RECORDS)

    logger.info(
        "DEMO MODE: Sample DataFrame ready",
        extra={
            "unique_managers": int(df["manager_firm"].nunique()),
            "total_rows": len(df),
            "total_aum_latest": f"${df['aum_latest_month'].sum():,.0f}",
        },
    )
    return df


__all__ = ["generate_sample_dataframe"]

import logging
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Tuple

import pandas as pd


logger = logging.getLogger(__name__)


@dataclass
class ReportDateWindow:
    """Represents a pair of prior/latest month-end dates for a report."""

    label: str  # e.g. "2026-02"
    prior_month_end: date
    latest_month_end: date


def _ensure_directory(path: Path) -> None:
    """
    Ensure that a directory exists.

    :param path: Directory path.
    """
    if not path.exists():
        logger.info("Creating directory", extra={"path": str(path)})
        path.mkdir(parents=True, exist_ok=True)


def _sanitize_manager_name(name: str) -> str:
    """
    Replace characters that are unsafe in file paths.

    :param name: Manager name from DB.
    :return: Filesystem-safe manager name.
    """
    return "".join(c for c in name if c not in r"<>:\"/\\|?*").strip()


def _build_report_filename(manager_name: str, label: str) -> str:
    """
    Build the Excel filename following the convention:
        ManagerName - YYYY-MM AUM Report.xlsx

    :param manager_name: Manager firm name.
    :param label: Month label in YYYY-MM format.
    """
    safe_name = _sanitize_manager_name(manager_name)
    return f"{safe_name} - {label} AUM Report.xlsx"


def generate_manager_reports(
    df: pd.DataFrame,
    output_root: Path,
    date_windows: List[ReportDateWindow],
) -> List[Tuple[str, Path]]:
    """
    Generate Excel reports per manager_firm for the given date windows.

    The same DataFrame is used for both windows, but each workbook includes
    metadata with the corresponding prior/latest month-end dates.

    :param df: DataFrame with at least columns manager_firm, aum_prior_month, aum_latest_month.
    :param output_root: Root output directory (e.g. ./output).
    :param date_windows: List of ReportDateWindow definitions to generate.
    :return: List of tuples (manager_firm, path_to_generated_file).
    """
    if df.empty:
        logger.warning("No data provided to generate_manager_reports; nothing will be generated")
        return []

    if "manager_firm" not in df.columns:
        raise ValueError("DataFrame must contain 'manager_firm' column")

    _ensure_directory(output_root)

    generated_files: List[Tuple[str, Path]] = []

    managers = sorted(df["manager_firm"].dropna().unique())
    logger.info(
        "Generating reports for managers",
        extra={"manager_count": len(managers)},
    )

    for manager in managers:
        manager_df = df[df["manager_firm"] == manager].reset_index(drop=True)
        safe_manager = _sanitize_manager_name(manager)
        manager_dir = output_root / safe_manager
        _ensure_directory(manager_dir)

        logger.info(
            "Generating reports for manager",
            extra={"manager_firm": manager, "rows": len(manager_df)},
        )

        for window in date_windows:
            filename = _build_report_filename(manager, window.label)
            file_path = manager_dir / filename

            logger.info(
                "Writing Excel report",
                extra={
                    "manager_firm": manager,
                    "file_path": str(file_path),
                    "label": window.label,
                    "prior_month_end": window.prior_month_end.isoformat(),
                    "latest_month_end": window.latest_month_end.isoformat(),
                },
            )

            # Write the manager-specific data to Excel with meta info on a summary sheet.
            with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
                # Detail sheet
                manager_df.to_excel(writer, sheet_name="AUM Data", index=False)

                # Summary sheet with dates and aggregate values
                summary_data = {
                    "metric": [
                        "manager_firm",
                        "prior_month_end",
                        "latest_month_end",
                    ],
                    "value": [
                        manager,
                        window.prior_month_end.isoformat(),
                        window.latest_month_end.isoformat(),
                    ],
                }
                summary_df = pd.DataFrame(summary_data)
                summary_df.to_excel(writer, sheet_name="Summary", index=False)

            generated_files.append((manager, file_path))

    logger.info(
        "Finished generating manager reports",
        extra={"file_count": len(generated_files)},
    )
    return generated_files


__all__ = ["ReportDateWindow", "generate_manager_reports"]


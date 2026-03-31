import logging
import shutil
from pathlib import Path


logger = logging.getLogger(__name__)


def cleanup_output_directory(output_root: Path) -> None:
    """
    Remove the local output directory and all its contents.

    :param output_root: Root output directory path (e.g. ./output).
    """
    if not output_root.exists():
        logger.info(
            "Output directory does not exist; nothing to clean up",
            extra={"output_root": str(output_root)},
        )
        return

    logger.info(
        "Deleting output directory and all generated files",
        extra={"output_root": str(output_root)},
    )
    try:
        shutil.rmtree(output_root)
    except Exception:  # noqa: BLE001
        logger.exception(
            "Failed to delete output directory",
            extra={"output_root": str(output_root)},
        )
        raise


__all__ = ["cleanup_output_directory"]


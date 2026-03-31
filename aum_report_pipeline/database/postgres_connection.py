import logging
import time
from contextlib import contextmanager
from typing import Iterator, Mapping, Any

import pandas as pd
import psycopg2
from psycopg2.extras import DictCursor

from aum_report_pipeline.config.aws_secrets import SecretsConfig


logger = logging.getLogger(__name__)


@contextmanager
def get_connection(secrets: SecretsConfig) -> Iterator[psycopg2.extensions.connection]:
    """
    Context manager that yields a PostgreSQL connection using psycopg2.

    :param secrets: SecretsConfig containing database credentials.
    """
    conn = None
    started = time.perf_counter()
    try:
        logger.info(
            "DB_CONNECT_START",
            extra={"host": secrets.postgres_host, "port": secrets.postgres_port, "db": secrets.postgres_db},
        )
        conn = psycopg2.connect(
            host=secrets.postgres_host,
            port=secrets.postgres_port,
            dbname=secrets.postgres_db,
            user=secrets.postgres_user,
            password=secrets.postgres_password,
            connect_timeout=20,
        )
        logger.info(
            "DB_CONNECT_SUCCESS",
            extra={"elapsed_seconds": round(time.perf_counter() - started, 3)},
        )
        yield conn
    except Exception:  # noqa: BLE001
        logger.exception(
            "DB_CONNECT_FAILED",
            extra={"elapsed_seconds": round(time.perf_counter() - started, 3)},
        )
        raise
    finally:
        if conn is not None:
            logger.info("Closing PostgreSQL connection")
            conn.close()


def run_query_to_dataframe(
    sql_path: str,
    secrets: SecretsConfig,
    params: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Execute the AUM SQL query and return the result as a pandas DataFrame.

    The query file must return the columns:
        manager_firm, aum_prior_month, aum_latest_month

    :param sql_path: Path to the SQL file containing the query.
    :param secrets: SecretsConfig with DB credentials.
    :param params: Optional mapping of SQL parameters (e.g. {'anchor_month': date}).
    :return: pandas DataFrame with query results.
    """
    logger.info(
        "Loading SQL query from file",
        extra={"sql_path": sql_path},
    )
    with open(sql_path, "r", encoding="utf-8") as f:
        query = f.read()

    with get_connection(secrets) as conn:
        try:
            logger.info(
                "DB_QUERY_START | Executing AUM query",
                extra={"has_params": bool(params)},
            )
            with conn.cursor(cursor_factory=DictCursor) as cur:
                query_started = time.perf_counter()
                cur.execute(query, params or None)
                rows = cur.fetchall()
                if not rows:
                    logger.warning("AUM query returned no rows")
                    return pd.DataFrame(columns=["manager_firm", "aum_prior_month", "aum_latest_month"])

                df = pd.DataFrame(rows, columns=rows[0].keys())
                logger.info(
                    "DB_QUERY_SUCCESS",
                    extra={"row_count": len(df), "elapsed_seconds": round(time.perf_counter() - query_started, 3)},
                )
                return df
        except Exception:  # noqa: BLE001
            logger.exception("Failed to execute AUM query")
            raise


__all__ = ["run_query_to_dataframe"]



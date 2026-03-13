import logging
from contextlib import contextmanager
from typing import Iterator

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
    try:
        logger.info(
            "Opening PostgreSQL connection",
            extra={"host": secrets.postgres_host, "db": secrets.postgres_db},
        )
        conn = psycopg2.connect(
            host=secrets.postgres_host,
            dbname=secrets.postgres_db,
            user=secrets.postgres_user,
            password=secrets.postgres_password,
        )
        yield conn
    except Exception:  # noqa: BLE001
        logger.exception("Error while connecting to PostgreSQL")
        raise
    finally:
        if conn is not None:
            logger.info("Closing PostgreSQL connection")
            conn.close()


def run_query_to_dataframe(sql_path: str, secrets: SecretsConfig) -> pd.DataFrame:
    """
    Execute the AUM SQL query and return the result as a pandas DataFrame.

    The query file must return the columns:
        manager_firm, aum_prior_month, aum_latest_month

    :param sql_path: Path to the SQL file containing the query.
    :param secrets: SecretsConfig with DB credentials.
    :return: pandas DataFrame with query results.
    """
    logger.info("Loading SQL query from file", extra={"sql_path": sql_path})
    with open(sql_path, "r", encoding="utf-8") as f:
        query = f.read()

    with get_connection(secrets) as conn:
        try:
            logger.info("Executing AUM query")
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(query)
                rows = cur.fetchall()
                if not rows:
                    logger.warning("AUM query returned no rows")
                    return pd.DataFrame(columns=["manager_firm", "aum_prior_month", "aum_latest_month"])

                df = pd.DataFrame(rows, columns=rows[0].keys())
                logger.info(
                    "AUM query executed successfully",
                    extra={"row_count": len(df)},
                )
                return df
        except Exception:  # noqa: BLE001
            logger.exception("Failed to execute AUM query")
            raise


__all__ = ["run_query_to_dataframe"]


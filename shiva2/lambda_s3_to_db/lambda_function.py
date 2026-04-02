import json
import logging
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import boto3
import psycopg2
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")
secrets_client = boto3.client("secretsmanager")

# Ingestion table name; DDL is applied from bundled schema.sql on each run (idempotent).
INGESTION_TABLE = "s3_file_records"


@dataclass
class DbConfig:
    host: str
    port: int
    dbname: str
    user: str
    password: str


@dataclass
class ParsedLine:
    line_number: int
    record_type: str
    source_type: str
    account_code: Optional[str]
    cusip: Optional[str]
    ticker: Optional[str]
    security_description: Optional[str]
    raw_line: str


def _safe_strip(value: str) -> Optional[str]:
    stripped = value.strip()
    return stripped if stripped else None


def _parse_source_type(lines: List[str]) -> str:
    if not lines:
        return "UNKNOWN"
    header = lines[0].upper()
    if "TASOPEN" in header:
        return "TASOPEN"
    if "TASCLOS" in header or "TASCLOSE" in header:
        return "TASCLOS"
    if "IFN DIRECTORY" in header:
        return "IFN_DIRECTORY"
    return "UNKNOWN"


def _parse_fixed_width_line(line: str, source_type: str, line_number: int) -> ParsedLine:
    record_type = line[:1]
    account_code = None
    cusip = None
    ticker = None
    security_description = None

    if source_type in ("TASOPEN", "TASCLOS"):
        account_code = _safe_strip(line[2:18]) if len(line) >= 18 else None
        cusip = _safe_strip(line[18:27]) if len(line) >= 27 else None
        security_description = _safe_strip(line[27:127]) if len(line) >= 127 else None
        ticker = _safe_strip(line[365:373]) if len(line) >= 373 else None
    elif source_type == "IFN_DIRECTORY":
        cusip = _safe_strip(line[1:10]) if len(line) >= 10 else None
        account_code = _safe_strip(line[10:13]) if len(line) >= 13 else None
        security_description = _safe_strip(line[185:245]) if len(line) >= 245 else None
        ticker = _safe_strip(line[2230:2235]) if len(line) >= 2235 else None

    return ParsedLine(
        line_number=line_number,
        record_type=record_type,
        source_type=source_type,
        account_code=account_code,
        cusip=cusip,
        ticker=ticker,
        security_description=security_description,
        raw_line=line.rstrip("\n"),
    )


def _extract_records(lines: List[str]) -> List[ParsedLine]:
    source_type = _parse_source_type(lines)
    parsed: List[ParsedLine] = []
    for i, line in enumerate(lines, start=1):
        if not line or line[0] != "D":
            continue
        parsed.append(_parse_fixed_width_line(line, source_type, i))
    return parsed


def _get_db_config() -> DbConfig:
    # Same hardcoded secret as AUM pipeline (aum_report_pipeline/main.py).
    secret_name = "callanOSbilling2"

    try:
        response = secrets_client.get_secret_value(SecretId=secret_name)
    except (ClientError, BotoCoreError) as exc:
        raise RuntimeError(f"Failed to read secret '{secret_name}'") from exc

    secret_string = response.get("SecretString")
    if not secret_string:
        raise RuntimeError(f"Secret '{secret_name}' does not have SecretString")

    data = json.loads(secret_string)
    required = ["host", "port", "database", "username", "password"]
    missing = [k for k in required if k not in data or data[k] in (None, "")]
    if missing:
        raise RuntimeError(f"Secret '{secret_name}' missing keys: {', '.join(missing)}")

    return DbConfig(
        host=data["host"],
        port=int(data["port"]),
        dbname=data["database"],
        user=data["username"],
        password=data["password"],
    )


def _db_connection():
    cfg = _get_db_config()
    return psycopg2.connect(
        host=cfg.host,
        port=cfg.port,
        dbname=cfg.dbname,
        user=cfg.user,
        password=cfg.password,
        connect_timeout=20,
    )


def _strip_sql_line_comments(sql: str) -> str:
    lines = []
    for line in sql.splitlines():
        stripped = line.split("--", 1)[0].rstrip()
        if stripped.strip():
            lines.append(stripped)
    return "\n".join(lines)


def _split_schema_statements(sql: str) -> List[str]:
    """Split schema.sql into executable statements (handles DO $$ ... END $$; blocks)."""
    sql = _strip_sql_line_comments(sql).strip()
    statements: List[str] = []
    i = 0
    n = len(sql)
    while i < n:
        while i < n and sql[i].isspace():
            i += 1
        if i >= n:
            break
        rest = sql[i:].lstrip()
        upper = rest[:20].upper()
        if upper.startswith("DO $$"):
            end = sql.find("END $$;", i)
            if end == -1:
                raise ValueError("schema.sql: unclosed DO $$ block (expected END $$;)")
            chunk = sql[i : end + len("END $$;")].strip()
            statements.append(chunk)
            i = end + len("END $$;")
            continue
        j = sql.find(";", i)
        if j == -1:
            tail = sql[i:].strip()
            if tail:
                statements.append(tail if tail.endswith(";") else tail + ";")
            break
        chunk = sql[i:j].strip()
        if chunk:
            statements.append(chunk + ";")
        i = j + 1
    return statements


def _load_schema_sql_text() -> str:
    """Load DDL from schema.sql next to this module (bundled in function zip)."""
    path = Path(__file__).resolve().parent / "schema.sql"
    if not path.is_file():
        raise RuntimeError(
            f"schema.sql not found at {path}. Include schema.sql in the Lambda deployment package."
        )
    return path.read_text(encoding="utf-8")


def _ensure_schema_and_log() -> None:
    """
    Connect, apply DDL from bundled schema.sql (idempotent), log result.
    CloudWatch: DB_SCHEMA_APPLY_*, DB_CONNECT_OK, DB_SCHEMA_OK.
    Requires DB user with CREATE TABLE / CREATE INDEX on the target schema (typically public).
    """
    cfg = _get_db_config()
    logger.info(
        "DB_CONNECT_START | host=%s port=%s dbname=%s user=%s | will ensure table=public.%s",
        cfg.host,
        cfg.port,
        cfg.dbname,
        cfg.user,
        INGESTION_TABLE,
    )
    schema_path = Path(__file__).resolve().parent / "schema.sql"
    logger.info("DB_SCHEMA_FILE | path=%s bundled=%s", schema_path, schema_path.is_file())

    ddl_text = _load_schema_sql_text()
    statements = _split_schema_statements(ddl_text)
    logger.info("DB_SCHEMA_APPLY_START | statement_count=%s", len(statements))
    conn = _db_connection()
    try:
        with conn.cursor() as cur:
            for idx, stmt in enumerate(statements, start=1):
                preview = stmt.replace("\n", " ")[:120]
                logger.info("DB_SCHEMA_APPLY_STATEMENT | n=%s | preview=%s", idx, preview)
                cur.execute(stmt)
            logger.info("DB_SCHEMA_APPLY_OK | applied_statements=%s", len(statements))
            logger.info(
                "DB_SCHEMA_TABLE_READY | public.%s ensured (CREATE IF NOT EXISTS + indexes + constraint)",
                INGESTION_TABLE,
            )
            cur.execute(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position
                """,
                (INGESTION_TABLE,),
            )
            columns = cur.fetchall()
        conn.commit()
        logger.info("DB_CONNECT_OK | connected to %s", cfg.dbname)
        logger.info(
            "DB_SCHEMA_OK | table=public.%s | column_count=%s | columns=%s",
            INGESTION_TABLE,
            len(columns),
            [c[0] for c in columns],
        )
    except Exception:
        logger.exception("DB_SCHEMA_APPLY_FAILED")
        raise
    finally:
        conn.close()


def _insert_records(bucket: str, key: str, records: Iterable[ParsedLine]) -> Tuple[int, int]:
    rows = [
        (
            bucket,
            key,
            r.line_number,
            r.record_type,
            r.source_type,
            r.account_code,
            r.cusip,
            r.ticker,
            r.security_description,
            r.raw_line,
        )
        for r in records
    ]
    if not rows:
        return 0, 0

    conn = _db_connection()
    inserted = 0
    try:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO s3_file_records (
                    s3_bucket,
                    s3_key,
                    line_number,
                    record_type,
                    source_type,
                    account_code,
                    cusip,
                    ticker,
                    security_description,
                    raw_line
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (s3_bucket, s3_key, line_number) DO NOTHING
                """,
                rows,
            )
            inserted = cur.rowcount if cur.rowcount != -1 else 0
        conn.commit()
    finally:
        conn.close()

    return inserted, len(rows)


def _should_process_key(key: str) -> bool:
    return key.lower().endswith(".dat")


def lambda_handler(event, context):
    logger.info("Received event: %s", json.dumps(event))
    _ensure_schema_and_log()

    total_inserted = 0
    files_processed = 0

    for event_record in event.get("Records", []):
        if event_record.get("eventSource") != "aws:s3":
            continue

        bucket = event_record["s3"]["bucket"]["name"]
        raw_key = event_record["s3"]["object"]["key"]
        key = urllib.parse.unquote_plus(raw_key)

        if not _should_process_key(key):
            logger.info("Skipping key outside pilot scope: s3://%s/%s", bucket, key)
            continue

        logger.info("Processing s3://%s/%s", bucket, key)
        response = s3_client.get_object(Bucket=bucket, Key=key)
        body = response["Body"].read()

        text = body.decode("latin-1", errors="replace")
        lines = text.splitlines()
        parsed_records = _extract_records(lines)
        inserted, attempted = _insert_records(bucket, key, parsed_records)

        logger.info(
            "Finished s3://%s/%s - attempted rows: %s, inserted rows: %s",
            bucket,
            key,
            attempted,
            inserted,
        )
        total_inserted += inserted
        files_processed += 1

    return {"statusCode": 200, "filesProcessed": files_processed, "rowsInserted": total_inserted}

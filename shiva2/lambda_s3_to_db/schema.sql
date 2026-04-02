-- Custodian ingestion: dedicated schema (separate from billing / other tables).
CREATE SCHEMA IF NOT EXISTS custodian;

CREATE TABLE IF NOT EXISTS custodian.s3_file_records (
    id BIGSERIAL PRIMARY KEY,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    s3_bucket TEXT NOT NULL,
    s3_key TEXT NOT NULL,
    line_number INT NOT NULL,
    record_type VARCHAR(1) NOT NULL,
    source_type VARCHAR(32) NOT NULL,
    account_code TEXT NULL,
    cusip TEXT NULL,
    ticker TEXT NULL,
    security_description TEXT NULL,
    raw_line TEXT NOT NULL
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        INNER JOIN pg_class t ON t.oid = c.conrelid
        INNER JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE c.conname = 'uq_s3_file_records_row'
          AND t.relname = 's3_file_records'
          AND n.nspname = 'custodian'
    ) THEN
        ALTER TABLE custodian.s3_file_records
            ADD CONSTRAINT uq_s3_file_records_row UNIQUE (s3_bucket, s3_key, line_number);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_s3_file_records_source
    ON custodian.s3_file_records (source_type, cusip, ticker);

CREATE INDEX IF NOT EXISTS idx_s3_file_records_s3_key
    ON custodian.s3_file_records (s3_bucket, s3_key);

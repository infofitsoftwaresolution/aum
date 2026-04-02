# S3 DAT Ingestion Lambda — Schema & Deployment Guide

This document describes the PostgreSQL schema used by the S3-triggered DAT ingestion Lambda, how to build deployment artifacts, and how to configure AWS (bucket `callan-sftp`, prefix `Fidelity/`).

---

## 1. Database schema

Run the following in the same PostgreSQL database as the AUM pipeline (credentials come from AWS Secrets Manager secret `callanOSbilling2` by default).

```sql
CREATE TABLE IF NOT EXISTS s3_file_records (
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
        FROM pg_constraint
        WHERE conname = 'uq_s3_file_records_row'
    ) THEN
        ALTER TABLE s3_file_records
            ADD CONSTRAINT uq_s3_file_records_row UNIQUE (s3_bucket, s3_key, line_number);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_s3_file_records_source
    ON s3_file_records (source_type, cusip, ticker);

CREATE INDEX IF NOT EXISTS idx_s3_file_records_s3_key
    ON s3_file_records (s3_bucket, s3_key);
```

- **Idempotency:** Inserts use `ON CONFLICT (s3_bucket, s3_key, line_number) DO NOTHING` so retries or re-uploads do not duplicate rows.

---

## 2. Build deployment zips (local)

From:

`D:\shivaproject\shiva2\lambda_s3_to_db`

```powershell
.\build-function.ps1
.\build-layer.ps1
```

| Output | Purpose |
|--------|---------|
| `s3-dat-ingestion-function.zip` | Lambda function code only |
| `s3-dat-ingestion-deps-layer.zip` | Dependencies (`psycopg2-binary`, etc.) |

**Requirements:**

- **Docker Desktop** must be running for `build-layer.ps1` (uses `public.ecr.aws/lambda/python:3.11`).
- Layer and Lambda runtime must both target **Python 3.11** to avoid binary import errors.

---

## 3. Create or update the Lambda function (AWS Console)

1. **Runtime:** Python 3.11  
2. **Handler:** `lambda_function.lambda_handler`  
3. **Upload code:** Upload `s3-dat-ingestion-function.zip`.  
4. **Layer:** Publish `s3-dat-ingestion-deps-layer.zip` as a Lambda Layer, then **attach** that layer to the function.  
5. **IAM role** must allow:
   - `s3:GetObject` on the source bucket (and prefix if you scope policies).  
   - `secretsmanager:GetSecretValue` on secret `callanOSbilling2` (or `Resource: "*` if your org allows it for this function).

---

## 4. Hardcoded configuration (same idea as AUM zip)

No Lambda environment variables are required for database or file filtering. Values are set in code, like `aum_report_pipeline/main.py` uses `secret_name = "callanOSbilling2"`.

| Setting | Value | Where |
|---------|--------|--------|
| Secrets Manager secret name | `callanOSbilling2` | `lambda_function.py` → `_get_db_config()` |
| Which files to ingest | Every `.dat` key that matches the S3 trigger (prefix/suffix you configure in S3 or SAM) | `lambda_function.py` → `_should_process_key()` |

The secret JSON must include `host`, `port`, `database`, `username`, `password` (same shape as the AUM pipeline).

---

## 5. S3 trigger (production path)

Target location:

- **Bucket:** `callan-sftp`  
- **Prefix:** `Fidelity/`

In **S3 → Bucket → Properties → Event notifications** (or via SAM `template.yaml`):

- **Event type:** Object created (all create events, or as needed).  
- **Prefix:** `Fidelity/`  
- **Suffix:** optional; the Lambda code only processes keys ending in `.dat` (case-insensitive).  
- **Destination:** this Lambda function.

---

## 6. Test flow

1. Upload a `.dat` file under `s3://callan-sftp/Fidelity/`.  
2. Open **CloudWatch Logs** for the function. You should see lines such as:
   - `Processing s3://callan-sftp/Fidelity/...`  
   - `attempted rows` and `inserted rows`  
3. Query PostgreSQL:

```sql
SELECT s3_bucket, s3_key, COUNT(*) AS row_count
FROM s3_file_records
GROUP BY s3_bucket, s3_key
ORDER BY MAX(ingested_at) DESC;
```

4. Re-upload the same file; row counts for existing line numbers should **not** increase (conflict handling).

---

## 7. SAM deploy (alternative)

From this folder, with AWS SAM CLI installed:

```bash
sam build
sam deploy --guided
```

Use parameters such as:

- `SourceBucketName` = `callan-sftp`  
- `SourcePrefix` = `Fidelity/`  
- `DbSecretName` = `callanOSbilling2`  
- `TargetDatKey` = leave empty or set for a single-file pilot  

See `template.yaml` for the full parameter list.

---

## 8. Related files in this repo

| File | Role |
|------|------|
| `lambda_function.py` | Handler, parsing, Secrets Manager, DB inserts |
| `schema.sql` | Same SQL as section 1 |
| `requirements.txt` | Layer dependencies |
| `template.yaml` | SAM template (S3 trigger, IAM) |
| `build-function.ps1` / `build-layer.ps1` | Zip builders |

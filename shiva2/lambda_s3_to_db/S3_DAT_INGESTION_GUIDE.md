# S3 DAT Ingestion Lambda — Schema & Deployment Guide

This document describes the PostgreSQL schema used by the S3-triggered DAT ingestion Lambda, how to build deployment artifacts, and how to configure AWS (bucket `callan-sftp`, prefix `Fidelity/`).

---

## 1. Database schema

The Lambda deployment zip includes **`schema.sql`** next to `lambda_function.py`. On **each invocation**, the function **applies this DDL** (idempotent):

1. **`CREATE SCHEMA IF NOT EXISTS custodian`** — keeps custodian data separate from billing / other schemas  
2. **`CREATE TABLE IF NOT EXISTS custodian.s3_file_records`** — raw ingestion table  
3. Unique constraint + indexes on **`custodian.s3_file_records`**

**If the schema or table does not exist yet, it is created on that run.** If they already exist, the same statements no-op safely.

**Database user:** The secret’s PostgreSQL user must be allowed to **`CREATE SCHEMA`**, **`CREATE TABLE`**, and **`CREATE INDEX`** (on database or at least on schema `custodian`).

Authoritative DDL: [schema.sql](schema.sql) in this folder (also bundled inside the function zip).

- **Idempotency:** Inserts use `ON CONFLICT (s3_bucket, s3_key, line_number) DO NOTHING` so retries or re-uploads do not duplicate rows.

### What the new table contains (`custodian.s3_file_records`)

| Column | Type | Meaning |
|--------|------|--------|
| `id` | `BIGSERIAL` | Surrogate primary key |
| `ingested_at` | `TIMESTAMPTZ` | When the row was inserted (default `NOW()`) |
| `s3_bucket` | `TEXT` | S3 bucket name for the source file |
| `s3_key` | `TEXT` | Full object key (path) in that bucket |
| `line_number` | `INT` | Line number in the `.dat` file (1-based) |
| `record_type` | `VARCHAR(1)` | First character of the line (e.g. `D` for data rows) |
| `source_type` | `VARCHAR(32)` | Parsed layout: `TASOPEN`, `TASCLOS`, `IFN_DIRECTORY`, or `UNKNOWN` |
| `account_code` | `TEXT` | Fixed-width field when applicable |
| `cusip` | `TEXT` | CUSIP when present |
| `ticker` | `TEXT` | Ticker when present |
| `security_description` | `TEXT` | Description field when present |
| `raw_line` | `TEXT` | Full source line (traceability) |

**Also created (if missing):** PostgreSQL schema **`custodian`**, unique constraint on `(s3_bucket, s3_key, line_number)`, and two indexes on `(source_type, cusip, ticker)` and `(s3_bucket, s3_key)`.

**Verify in SQL:** `SELECT * FROM custodian.s3_file_records LIMIT 5;` or `\dn custodian` / `\dt custodian.*` in `psql`.

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
| `s3-dat-ingestion-function.zip` | Lambda code + bundled `schema.sql` (DDL applied at runtime) |
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
2. Open **CloudWatch Logs** for the function. On each run, the function **applies schema from the zip** then logs:
   - `DB_SCHEMA_FILE` — path to bundled `schema.sql` in the runtime
   - `DB_SCHEMA_APPLY_START` / `DB_SCHEMA_APPLY_STATEMENT` / `DB_SCHEMA_APPLY_OK` — DDL executed
   - `DB_CONNECT_OK` — after commit
   - `DB_SCHEMA_OK` — column list read from `information_schema` (verify in DB with `\d custodian.s3_file_records` or the SQL below)
   Then, per file:
   - `Processing s3://callan-sftp/Fidelity/...`  
   - `attempted rows` and `inserted rows`  
3. Query PostgreSQL:

```sql
SELECT s3_bucket, s3_key, COUNT(*) AS row_count
FROM custodian.s3_file_records
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

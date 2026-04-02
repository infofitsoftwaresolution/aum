# S3 DAT Ingestion Lambda

This package contains a separate Lambda for S3 `.dat` ingestion into PostgreSQL.
It reads DB credentials from AWS Secrets Manager secret **`callanOSbilling2`**, hardcoded in `lambda_function.py` (same pattern as `aum_report_pipeline/main.py`).

## What it does

- Trigger on S3 object created events
- Process only `.dat` files (case-insensitive check in code)
- Processes every `.dat` file delivered by the S3 trigger (prefix configured in S3/SAM)
- Parse fixed-width `D` rows and store normalized fields + `raw_line`
- Insert idempotently with uniqueness on `(s3_bucket, s3_key, line_number)`
- On each cold start / invocation, applies **`schema.sql`** from the deployment package (creates table, indexes, constraint if missing)

## Files

- `lambda_function.py` - Handler, parser, secrets lookup, DDL apply, DB insert logic
- `schema.sql` - Bundled in the function zip; applied automatically at runtime (idempotent)
- `template.yaml` - AWS SAM template for S3 trigger and IAM
- `requirements.txt` - Python layer dependencies
- `build-function.ps1` - Creates `s3-dat-ingestion-function.zip` (`lambda_function.py` + `schema.sql`)
- `build-layer.ps1` - Creates `s3-dat-ingestion-deps-layer.zip` (dependencies)

## 1) Database permissions

The Postgres user from Secrets Manager needs **`CREATE SCHEMA`** / **`CREATE TABLE`** / **`CREATE INDEX`** so the Lambda can apply `schema.sql` (creates schema **`custodian`** and table **`custodian.s3_file_records`**).

## 2) Build deployment artifacts

From `D:\shivaproject\shiva2\lambda_s3_to_db`:

```powershell
.\build-function.ps1
.\build-layer.ps1
```

Notes:
- `build-layer.ps1` requires Docker Desktop running.
- Runtime/build alignment is set to Python 3.11.

## 3) Deploy Lambda

### Option A: SAM

```bash
sam build
sam deploy --guided
```

Provide:
- `SourceBucketName` - source bucket
- `SourcePrefix` - S3 key prefix for the trigger (default `Fidelity/`)

### Option B: Console/CLI zip deployment

- Upload `s3-dat-ingestion-function.zip` as function code
- Publish `s3-dat-ingestion-deps-layer.zip` as a Lambda Layer
- Attach the layer to the function
- Set handler to `lambda_function.lambda_handler`
- Set runtime to Python 3.11
- No environment variables required for DB (secret name is hardcoded in code)

## 4) Verification checklist

1. Upload one test `.dat` file to the configured bucket/prefix.
2. Check CloudWatch logs for:
   - `DB_SCHEMA_APPLY_OK` (DDL from bundled `schema.sql`)
   - `DB_SCHEMA_OK` (column list)
   - `Processing s3://...`
   - `attempted rows` and `inserted rows`
3. Validate rows in PostgreSQL:

```sql
SELECT s3_bucket, s3_key, COUNT(*) AS row_count
FROM custodian.s3_file_records
GROUP BY s3_bucket, s3_key
ORDER BY MAX(ingested_at) DESC;
```

4. Re-upload same file and confirm dedupe (row count does not increase for same line numbers).

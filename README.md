## AUM Report Pipeline

Automated Python pipeline to generate AUM (Assets Under Management) reports per manager, upload them to S3, and clean up local files.

### Overview

The pipeline:

- **Retrieves credentials from AWS Secrets Manager**
- **Connects to PostgreSQL** and runs an AUM query
- **Converts results into a pandas dataframe**
- **Generates per-manager Excel reports** for the last two month windows
- **Uploads reports to S3** under the required folder structure
- **Deletes all local generated files** after successful upload

### Project Structure

```text
aum_report_pipeline/
  config/
    aws_secrets.py
  database/
    postgres_connection.py
  reports/
    report_generator.py
  s3/
    s3_uploader.py
  utils/
    cleanup.py
  queries/
    aum_query.sql
  main.py
requirements.txt
README.md
```

### Prerequisites

- **Python 3.11**
- **Access to AWS** with permission to read from Secrets Manager and write to S3
- **Network access to PostgreSQL**

### Installation

1. **Create and activate a virtual environment**

   ```bash
   cd path/to/Project/ShivaProject
   python -m venv .venv
   .venv\Scripts\activate  # on Windows
   # source .venv/bin/activate  # on macOS/Linux
   ```

2. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

### AWS Secrets Manager Setup

Create a single secret in AWS Secrets Manager (JSON format) with at least the following keys:

```json
{
  "postgres_host": "your-postgres-host",
  "postgres_db": "your-database-name",
  "postgres_user": "your-db-user",
  "postgres_password": "your-db-password",
  "aws_access_key": "your-aws-access-key-or-null",
  "aws_secret_key": "your-aws-secret-key-or-null",
  "s3_bucket_name": "your-s3-bucket-name"
}
```

Note:

- If you are using **IAM roles** or default AWS credentials, you may set `aws_access_key` and `aws_secret_key` to `null`, and the app will fall back to the default credential chain for initial Secrets Manager access and S3 uploads.

### Environment Variables

You can use a local `.env` file (via `python-dotenv`) or set these in your environment:

- **Required**
  - `AWS_REGION` or `AWS_DEFAULT_REGION` – AWS region for Secrets Manager and S3
  - `AWS_SECRETS_NAME` – Name of the secret in AWS Secrets Manager

- **Optional**
  - `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` – AWS access keys for local development (otherwise default AWS credentials/roles are used)
  - `OUTPUT_DIR` – Local directory to write reports (default: `<project_root>/output`)
  - `LOG_LEVEL` – Logging level (`INFO`, `DEBUG`, etc., default `INFO`)

Example `.env`:

```env
AWS_REGION=us-east-1
AWS_SECRETS_NAME=aum-report-secrets
AWS_ACCESS_KEY_ID=your-aws-access-key-id
AWS_SECRET_ACCESS_KEY=your-aws-secret-access-key
OUTPUT_DIR=output
LOG_LEVEL=INFO
```

### PostgreSQL Query

`aum_report_pipeline/queries/aum_query.sql` is parameterised by an `anchor_month` date.  
For each reporting window, the pipeline calls the query with a different `anchor_month` so that:

- `latest_month_end` = last business day of the anchor month
- `prior_month_end` = last business day of the month before the anchor month

The query **must** return at least these columns:

- `manager_firm`
- `aum_prior_month`
- `aum_latest_month`

The supplied query uses the `sleeve_allocations`, `aum_daily_values`, and `product_master` tables, and should be adapted to your schema as needed.

### Report Generation Logic

- The pipeline computes **two reporting windows** based on the current date:
  - **Latest month**: prior = month-end two months ago, latest = month-end last month
  - **Previous month**: prior = month-end three months ago, latest = month-end two months ago
- For each `manager_firm`, the pipeline:
  - Creates `./output/<ManagerName>/`
  - Writes:
    - `ManagerName - YYYY-MM AUM Report.xlsx` for each of the two windows
  - Each workbook contains:
    - `AUM Data` sheet: rows for that manager from the query
    - `Summary` sheet: `manager_firm`, `prior_month_end`, `latest_month_end`

### S3 Folder Structure

Files are uploaded to S3 as:

```text
s3://<bucket>/managers/<ManagerName>/<ManagerName - YYYY-MM AUM Report.xlsx>
```

Where `<ManagerName>` is a sanitized version of `manager_firm` (unsafe path characters removed).

### Running the Pipeline

From the project root (`ShivaProject`):

```bash
python -m aum_report_pipeline.main
```

Or, directly:

```bash
python aum_report_pipeline/main.py
```

### Logging & Error Handling

- Uses Python's `logging` module with a simple structured format:
  - `timestamp | level | logger | message`
- Logs:
  - Secret retrieval
  - Database connection and query execution
  - Report generation progress and file paths
  - S3 uploads
  - Cleanup actions
- Any unhandled exception in the pipeline is logged and causes the process to exit with a non-zero status.


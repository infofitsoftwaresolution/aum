# AUM Report Pipeline - AWS Lambda Deployment Guide

This document explains how to deploy and run this project from AWS Lambda using an IAM role (no AWS access key/secret key in code).

## 1) Current project structure

- Entry point: `main.py`
- Secrets manager module: `config/aws_secrets.py`
- PostgreSQL module: `database/postgres_connection.py`
- Excel generation: `reports/report_generator.py`
- S3 upload: `s3/s3_uploader.py`
- SQL file: `queries/aum_query.sql`

## 2) Important architecture changes for Lambda

Before deployment, make these changes:

1. Remove dependency on long-lived AWS keys from secret and code.
2. Use Lambda execution role for AWS API calls.
3. Ensure secrets only contain DB + S3 config values.
4. Keep package size small (Lambda zip upload limit is 50 MB).

### 2.1 Required updates in `config/aws_secrets.py`

Your current codebase expects DB credentials to come from `config/aws_secrets.py`.

Based on your screenshot, your Secrets Manager JSON keys are:

- `host`
- `port`
- `database`
- `username`
- `password`

For Lambda role-based auth, you should **not** store or require long-lived AWS access keys in that secret.

### 2.2 Required updates in `s3/s3_uploader.py`

Always create S3 client using default boto3 session (Lambda role), not secret-stored keys.

### 2.3 Environment loading in Lambda

`python-dotenv` is optional in Lambda. Environment variables are supplied directly by Lambda.

## 3) Secrets Manager setup

Create or edit secret: `callanOSbilling2`

Use JSON with this shape (must match exactly; keys are case-sensitive):

```json
{
  "host": "callanos-billing-db.ce784qukw512.us-east-1.rds.amazonaws.com",
  "port": "5432",
  "database": "postgres",
  "username": "postgres",
  "password": "<password>",
  "s3_bucket_name": "<your-report-bucket>"
}
```

Notes:
- Keep key names exactly matching the ones above (they are mapped in `config/aws_secrets.py`).
- For fully "no env vars" Lambda execution, `s3_bucket_name` is required inside this secret.

## 4) IAM role for Lambda

Attach an execution role to Lambda with minimum permissions:

- `secretsmanager:GetSecretValue` for secret `callanOSbilling2`
- `s3:PutObject` (and optional `s3:AbortMultipartUpload`) for report bucket/prefix
- CloudWatch Logs permissions

Example policy template:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue"],
      "Resource": "arn:aws:secretsmanager:us-east-1:<ACCOUNT_ID>:secret:callanOSbilling2-*"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:AbortMultipartUpload"],
      "Resource": "arn:aws:s3:::<BUCKET_NAME>/managers/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "*"
    }
  ]
}
```

If KMS encryption is used, also add `kms:Decrypt` on the relevant key.

## 5) Minimal libraries for Lambda

Use only mandatory dependencies.

Recommended `requirements-lambda.txt`:

```text
psycopg2-binary==2.9.9
pandas==2.2.2
openpyxl==3.1.2
```

Notes:
- `boto3` should not be packaged; Lambda runtime already includes it.
- If package gets too large with pandas/psycopg2, consider Lambda container image deployment.

## 6) VPC and networking (for private RDS)

If RDS is private:

1. Configure Lambda in same VPC.
2. Choose subnets with route to DB.
3. Lambda security group must allow outbound to DB SG on port 5432.
4. Ensure Lambda can reach AWS APIs:
   - NAT gateway, or
   - VPC endpoints for Secrets Manager and S3.

## 7) Lambda handler wiring

Create/update `lambda_handler.py` inside the `aum_report_pipeline/` package:

```python
from aum_report_pipeline.main import main


def handler(event, context):
    main()
    return {"statusCode": 200, "body": "AUM pipeline executed successfully"}
```

Lambda handler value:

- `aum_report_pipeline.lambda_handler.handler`

## 8) Environment variables in Lambda

No environment variables are required.

Optional:
- `LOG_LEVEL` (default `INFO`)

Lambda writable path is `/tmp` only.

## 9) Build and package (Windows + Docker recommended)

Because Lambda runs on Linux, build dependencies in Linux-compatible environment.

Important: your code imports use the package name `aum_report_pipeline`, so the zip must preserve the `aum_report_pipeline/` folder.

From the parent folder `C:\\Users\\anilu\\Projects\\shivaproject`:

```powershell
cd C:\\Users\\anilu\\Projects\\shivaproject

docker run --rm -v "${PWD}:/var/task" public.ecr.aws/lambda/python:3.12 bash -lc "
  rm -rf /var/task/build && mkdir -p /var/task/build/aum_report_pipeline && \
  pip install -r /var/task/aum_report_pipeline/requirements-lambda.txt -t /var/task/build/aum_report_pipeline && \
  cp -r /var/task/aum_report_pipeline/* /var/task/build/aum_report_pipeline/
"

Compress-Archive -Path .\\build\\* -DestinationPath .\\aum-report-lambda.zip -Force
```

## 10) Create Lambda function (Console)

1. Go to AWS Lambda > Create function.
2. Runtime: Python 3.12.
3. Execution role: attach the IAM role from section 4.
4. Upload `aum-report-lambda.zip`.
5. Set handler to `aum_report_pipeline.lambda_handler.handler`.
6. Configure timeout (start with 3-5 min) and memory (start with 1024 MB).
7. Configure VPC if needed.
8. No environment variables are required (see section 8).

## 11) Test execution

1. Create a test event `{}`.
2. Run test.
3. Check CloudWatch logs for:
   - secret retrieval success
   - query execution success
   - report generation count
   - S3 upload success
4. Verify files in S3 path:
   - `s3://<bucket>/managers/<ManagerName>/<file>.xlsx`

## 12) Schedule execution

Use EventBridge rule to run monthly/daily.

Example cron (1st day every month, 02:00 UTC):

- `cron(0 2 1 * ? *)`

Attach this rule as Lambda trigger.

## 13) Troubleshooting

- `No module named psycopg2`:
  - Package built on Windows; rebuild in Linux Docker.
- Secret key missing error:
  - Secret JSON keys do not match expected names.
- Timeout connecting to DB:
  - VPC/Security group/NAT endpoint issue.
- Access denied to S3/Secrets:
  - IAM role policy missing correct ARN or action.

## 14) Security best practices

- Never store AWS access keys in code, env, or secret.
- Use IAM role with least privilege.
- Restrict S3 permissions to required prefix only.
- Rotate DB credentials in Secrets Manager.


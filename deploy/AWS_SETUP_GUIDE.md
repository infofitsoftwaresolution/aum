# AWS Console Setup Guide — AUM Report Pipeline on Lambda

> **This guide is split into two tracks. Start with the Demo Track.**
>
> - 🟢 **Demo Track** (Steps 1–6) — No PostgreSQL, no RDS, no Secrets Manager. Just S3 + Lambda.
> - 🔵 **Production Track** (Appendix A) — Full pipeline with PostgreSQL + Secrets Manager.

---

## ⚠️ Before You Start — Find Your AWS Account ID

AWS Account IDs are **exactly 12 digits with NO dashes** (e.g. `123456789012`).

**How to find it:**
> AWS Console → click your **account name / email** in the **top-right corner** → copy the 12-digit number shown under "Account ID"

You will need this when creating IAM policies. A common mistake is copying it with dashes — always remove them.

---

## Prerequisites Checklist (Demo Track)

- [ ] AWS account access (admin or IAM + Lambda + S3 permissions)
- [ ] AWS CLI installed → `aws --version`
- [ ] Python 3.11 installed → `python --version`
- [ ] S3 bucket created for demo output (e.g. `aum-demo-reports-shubham`)

---

---

# 🟢 DEMO TRACK — Run Without Any Database

> Uses synthetic sample data. No PostgreSQL, no RDS, no Secrets Manager required.
> Lambda environment variable `DEMO_MODE=true` activates this path automatically.

---

## Step 1 — Create an S3 Bucket

**Go to**: AWS Console → S3 → **Create bucket**

- Bucket name: `aum-demo-reports-shubham` (or any name you choose — must be globally unique)
- Region: `ap-south-1`
- Block all public access: ✅ Keep enabled (default)
- Click **Create bucket**

> Note your bucket name — you'll need it as a Lambda environment variable.

---

## Step 2 — Create the Lambda IAM Role

**Go to**: AWS Console → IAM → Roles → **Create Role**

1. **Trusted entity type**: AWS Service
2. **Use case**: Lambda
3. Click **Next**
4. Search and attach the managed policy: `AWSLambdaBasicExecutionRole`
5. Click **Next** → Role name: `aum-report-pipeline-role`
6. Click **Create Role**

### Add Inline Policy (Demo Permissions)

Open the role you just created → **Add permissions** → **Create inline policy** → **JSON** tab

Paste this policy (it's already saved in `deploy/iam_policy.json`):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowS3ReportsWrite",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:PutObjectAcl"
      ],
      "Resource": "arn:aws:s3:::aum-demo-reports-shubham/managers/*"
    },
    {
      "Sid": "AllowCloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    }
  ]
}
```

---

## Step 3 — Create the Lambda Function

**Go to**: AWS Console → Lambda → **Create function**

- **Author from scratch**
- Function name: `aum-report-pipeline`
- Runtime: **Python 3.11**
- Architecture: **x86_64**
- Permissions: **Use an existing role** → select `aum-report-pipeline-role`
- Click **Create function**

---

## Step 4 — Configure the Lambda Function

### 4A — Configuration Settings

**Part 1: General configuration** (Memory & Timeout)
1. **Configuration tab** → **General configuration** → **Edit**.
2. Set **Memory**: `512 MB`.
3. Set **Ephemeral storage**: `1024 MB`.
4. Set **Timeout**: `10 min 0 sec`.
5. Click **Save**.

**Part 2: Runtime settings** (The Handler)
1. **Configuration tab** → **Runtime settings** (in the left sidebar).
2. Click **Edit**.
3. Set **Handler**: `aum_report_pipeline.lambda_handler.handler`.
4. Click **Save**.

---

### 4B — Set Environment Variables

**Configuration tab** → **Environment variables** → **Edit** → **Add environment variable**:

| Key | Value | Notes |
|---|---|---|
| `DEMO_MODE` | `true` | Activates demo path — no DB needed |
| `S3_BUCKET_NAME` | `aum-demo-reports-shubham` | Your bucket name |
| `LOG_LEVEL` | `INFO` | Or `DEBUG` for verbose output |

Click **Save**.

> ❌ Do NOT add `AWS_REGION` — Lambda provides this automatically.
> ❌ Do NOT add `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` — Lambda uses the IAM role.

---

### 4C — Reserved Concurrency

Prevents two simultaneous pipeline runs from conflicting.

**Configuration tab** → **Concurrency** → **Edit**:
1. Select **Reserve concurrency**.
2. Value: **1**.
3. Click **Save**.

---

## Step 5 — Deploy the Code

Open **PowerShell** in `d:\shivaproject`:

```powershell
# Set variables in deploy\build_lambda.ps1 if needed
.\deploy\build_lambda.ps1
```

---

## Step 6 — Test the Lambda

Go to Lambda → `aum-report-pipeline` → **Test** tab:
- Event name: `demo-test`
- Event JSON: `{}`
- Click **Test**

**Expected logs**:
- `DEMO MODE ENABLED`
- `AUM report pipeline completed successfully`

---

# 🔵 PRODUCTION TRACK (Appendix A)

> Switch from demo to production when you have real PostgreSQL data.

## A1 — AWS Secrets Manager Setup

JSON structure:
```json
{
  "postgres_host": "...",
  "postgres_db": "...",
  "postgres_user": "...",
  "postgres_password": "...",
  "aws_access_key": null,
  "aws_secret_key": null,
  "s3_bucket_name": "..."
}
```

## A2 — Update IAM Policy
Add `secretsmanager:GetSecretValue` and `secretsmanager:DescribeSecret` permissions.

## A3 — Update Env Vars
Set `DEMO_MODE=false` and add `AWS_SECRETS_NAME`.

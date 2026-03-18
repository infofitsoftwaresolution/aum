# AWS Console Setup Guide — PRODUCTION TRACK (Real Database)

This guide connects your Lambda function to the real PostgreSQL database
using the `aum-report-secrets` secret set up by your team lead.

---

## ✅ Key Values (confirmed from your team lead's IAM policy)

| Setting | Value |
|---|---|
| **Secret Name** | `aum-report-secrets` |
| **AWS Region** | `us-east-1` |
| **S3 Bucket** | `aris-data-extracts` |
| **Account ID** | `650089954417` |

> ⚠️ **Your Lambda function MUST also be created in `us-east-1`!**
> If it's in `ap-south-1`, it won't be able to access the secret or the S3 bucket.

---

## Step 1 — Create Lambda in `us-east-1`

**Go to**: AWS Console → Make sure region is **US East (N. Virginia) = `us-east-1`** (top-right corner).

Lambda → **Create function**:
- Function name: `aum-report-pipeline`
- Runtime: **Python 3.11**
- Architecture: `x86_64`
- Execution role → **Use an existing role** → Select `aum-report-pipeline-role` (your team lead's role).
- Click **Create function**.

---

## Step 2 — Configure Runtime Settings

**Configuration tab** → **Runtime settings** → **Edit**:
- Handler: `aum_report_pipeline.lambda_handler.handler`
- Click **Save**.

---

## Step 3 — Configure General Settings

**Configuration tab** → **General configuration** → **Edit**:
- Memory: `512 MB`
- Ephemeral storage: `1024 MB`
- Timeout: `10 min 0 sec`
- Click **Save**.

---

## Step 4 — Set Environment Variables

**Configuration tab** → **Environment variables** → **Edit** → **Add environment variable**:

| Key | Value |
|---|---|
| `DEMO_MODE` | `false` |
| `AWS_SECRETS_NAME` | `aum-report-secrets` |
| `S3_BUCKET_NAME` | `aris-data-extracts` |
| `LOG_LEVEL` | `INFO` |

Click **Save**.

> ❌ Do NOT add `AWS_REGION` — this is a reserved key; Lambda sets it automatically.
> ❌ Do NOT add `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` — Lambda uses the IAM role.

---

## Step 5 — Attach the psycopg2 Lambda Layer

To connect to PostgreSQL, Lambda needs a compiled driver.

1. Scroll to **Layers** section on the Lambda page.
2. Click **Add a layer** → **Specify an ARN**.
3. Ask your team lead for the `psycopg2` Layer ARN (or use a public one for `us-east-1`):
   ```
   arn:aws:lambda:us-east-1:898466741470:layer:psycopg2-py311:2
   ```
4. Click **Verify** → **Add**.

---

## Step 6 — VPC Configuration (if DB is in a private network)

**Configuration tab** → **VPC** → **Edit**:
- VPC: Select the same VPC as the database.
- Subnets: At least 2 private subnets.
- Security Groups: Allow outbound TCP on port `5432`.
- Click **Save**.

*(Skip this if your DB is publicly accessible).*

---

## Step 7 — Deploy the Code

**Build the ZIP**:
```powershell
cd d:\shivaproject
.\deploy\build_lambda.ps1
```

**Upload to Lambda**:
- Lambda Console → `aum-report-pipeline` → **Code** tab.
- Click **Upload from** → **.zip file**.
- Select `build\aum_lambda.zip` → Click **Save**.

---

## Step 8 — Test

Lambda → `aum-report-pipeline` → **Test** tab:
- Event name: `prod-test`
- Event JSON: `{}`
- Click **Test**

**Expected logs in CloudWatch**:
```
Retrieving secrets for 'aum-report-secrets'
Successfully retrieved secrets for 'aum-report-secrets'
Step 2: Computing reporting windows
Step 3: Executing AUM queries and generating Excel reports
AUM report pipeline completed successfully
```

**Check S3**: `aris-data-extracts` bucket → confirm `.xlsx` files appear under `managers/`.

---

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `UnrecognizedClientException` | Lambda is in the wrong AWS region | Delete function and recreate in `us-east-1` |
| `ResourceNotFoundException` on secret | `AWS_SECRETS_NAME` value is wrong | Must be exactly `aum-report-secrets` |
| `AccessDenied` on secretsmanager | Wrong role attached to Lambda | Go to Configuration → Permissions and confirm the role containing the team lead's policy is shown |
| `psycopg2 not found` | psycopg2 Layer not attached | Repeat Step 5 |
| `Connection refused on port 5432` | Lambda not in same VPC as DB | Complete Step 6 |
| `S3 PutObject AccessDenied` | Wrong Lambda region OR wrong bucket name | Confirm Lambda is in `us-east-1` and `S3_BUCKET_NAME=aris-data-extracts` |

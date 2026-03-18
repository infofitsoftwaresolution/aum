# AWS Console Setup Guide — PRODUCTION TRACK (Real Database)

This guide takes the AUM Report Pipeline out of "Demo Mode" and connects it to the real PostgreSQL database using the `callanOSbilling2` secret provided by your team lead.

---

## Prerequisites Checklist

- [x] Lambda function `aum-report-pipeline` deployed with `.zip` package.
- [x] S3 bucket ready for uploads (e.g., `aris-data-extracts`).
- [x] AWS Secret `callanOSbilling2` exists in AWS Secrets Manager.

---

## Step 1 — Update the Lambda IAM Role (Permissions)

Your Lambda needs permission to read the real database credentials from AWS Secrets Manager.

**Go to**: AWS Console → IAM → Roles → find exactly `aum-report-pipeline-role`.

1. Click **Add permissions** → **Create inline policy**.
2. Switch to the **JSON** tab and paste this exactly:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
       "Effect": "Allow",
       "Action": "secretsmanager:GetSecretValue",
       "Resource": "arn:aws:secretsmanager:us-east-1:*:secret:callanOSbilling2-*"
    }
  ]
}
```
*(Note: If the secret is in `ap-south-1`, change the region in the `Resource` string).*
3. Click **Next**, name the policy `Production-Secrets-Access`, and click **Create Policy**.

---

## Step 2 — Attach the PostgreSQL Lambda Layer

`psycopg2` requires compiled C code to connect to PostgreSQL. AWS Lambda (Amazon Linux) rejects the Windows version bundled by `pip`. **You MUST attach a Lambda Layer.**

**Go to**: AWS Console → Lambda → `aum-report-pipeline`.

1. Scroll down to the **Layers** section (at the very bottom).
2. Click **Add a layer**.
3. Choose **Specify an ARN**.
4. Paste the ARN of a `psycopg2` layer for Python 3.11 in your AWS region.
   *(Ask your Team Lead for their psycopg2 Layer ARN, or you can find public ones online like `arn:aws:lambda:us-east-1:816281081515:layer:psycopg2-py311:1`)*
5. Click **Verify**, then **Add**.

---

## Step 3 — VPC Configuration (Important!)

If the real database is sitting inside a private network, Lambda needs to be moved inside that network to talk to it.

**Configuration tab** → **VPC** → **Edit**:
- **VPC**: Select the VPC that hosts your `callanOSbilling2` database.
- **Subnets**: Select at least 2 private subnets.
- **Security Groups**: Select a security group that allows outbound connections on port `5432` (PostgreSQL).
- Click **Save**. *(Skip this step if your database is publicly accessible over the internet via an IP/DNS).*

---

## Step 4 — Flip the Environment Switches

Turn off Demo Mode and tell the code which Secret to read.

**Configuration tab** → **Environment variables** → **Edit**:

| Key | Value | Notes |
|---|---|---|
| `DEMO_MODE` | `false` | This turns OFF the synthetic demo data. |
| `AWS_SECRETS_NAME` | `callanOSbilling2` | The exact name of your Team Lead's secret. |
| `S3_BUCKET_NAME` | `aris-data-extracts` | Or whatever your real S3 bucket is. |
| `LOG_LEVEL` | `INFO` | Or `DEBUG` for verbose output. |

Click **Save**.

---

## Step 5 — Deploy and Test

**1. Generate the Zip**
Open **PowerShell** in your project directory and run:
```powershell
.\deploy\build_lambda.ps1
```
*(This zips up the new `aws_secrets.py` fix we just added which adapts to the `callanOSbilling2` schema).*

**2. Test the Lambda**
Go to Lambda → `aum-report-pipeline` → **Test** tab:
- Event name: `production-test`
- Event JSON: `{}`
- Click **Test**

**Expected output logs**:
- `Retrieving secrets for 'callanOSbilling2'`
- `Executing AUM queries via postgres...`
- `Reports generated for X schemas`
- `Upload complete to s3://aris-data-extracts/managers/...`

# AUM Report Pipeline - Lambda Layers Deployment Guide (Beginner Friendly)

This guide shows how to deploy this project using **AWS Lambda Layers** for Python dependencies.

Goal:
- Keep Lambda function zip small
- Put heavy dependencies (`pandas`, `psycopg2-binary`, `openpyxl`) into a Layer
- Upload only project code as the function zip

---

## 1) What is a Lambda Layer?

A Layer is a separate zip package that Lambda mounts at runtime under `/opt`.
For Python, dependencies must be under:

- `python/` (inside layer zip)

When the function starts, Python automatically includes `/opt/python` in `sys.path`.

---

## 2) Your current project setup

Project root:
- `C:\Users\anilu\Projects\shivaproject\aum_report_pipeline`

Important files:
- `requirements-lambda.txt` (dependencies for layer)
- `lambda_handler.py` (Lambda entrypoint)
- `main.py` (pipeline orchestration)

Current handler value:
- `aum_report_pipeline.lambda_handler.handler`

---

## 3) Prerequisites

1. Docker Desktop installed and running (required to build Linux-compatible wheels on Windows).
2. AWS Lambda function already created with execution role attached.
3. Role permissions include at least:
   - `secretsmanager:GetSecretValue` (for `callanOSbilling2`)
   - `s3:PutObject` (for `aris-data-extracts/managers/*`)
   - CloudWatch logs permissions
4. Runtime in Lambda should match build runtime (use Python 3.12 in this guide).

---

## 4) Build Layer zip (dependencies only)

Open PowerShell and run from parent folder:

```powershell
Set-Location "C:\Users\anilu\Projects\shivaproject"

# Clean old artifacts
if (Test-Path ".\layer_build") { Remove-Item ".\layer_build" -Recurse -Force }
if (Test-Path ".\aum-report-deps-layer.zip") { Remove-Item ".\aum-report-deps-layer.zip" -Force }

# Build dependencies in Linux Lambda image
# IMPORTANT: layer structure must be layer_build/python/
docker run --rm --entrypoint /bin/bash `
  -v "${PWD}:/var/task" `
  public.ecr.aws/lambda/python:3.12 `
  -lc "
    set -e
    rm -rf /var/task/layer_build
    mkdir -p /var/task/layer_build/python

    pip install -r /var/task/aum_report_pipeline/requirements-lambda.txt \
      -t /var/task/layer_build/python

    # optional cleanup
    find /var/task/layer_build -type d -name '__pycache__' -exec rm -rf {} +
    find /var/task/layer_build -type d -name 'tests' -exec rm -rf {} +
  "

# Create layer zip
Compress-Archive -Path ".\layer_build\*" -DestinationPath ".\aum-report-deps-layer.zip" -Force

# Show zip size
$sizeMB = (Get-Item ".\aum-report-deps-layer.zip").Length / 1MB
Write-Host ("Layer zip created: aum-report-deps-layer.zip | Size: {0:N2} MB" -f $sizeMB)
```

---

## 5) Publish Layer in AWS Lambda Console

1. AWS Console -> Lambda -> **Layers** -> **Create layer**.
2. Name: `aum-report-deps-py312` (example).
3. Upload: `aum-report-deps-layer.zip`.
4. Compatible runtimes: **Python 3.12**.
5. Create.

After creation, note Layer ARN/version, for example:
- `arn:aws:lambda:us-east-1:123456789012:layer:aum-report-deps-py312:1`

---

## 6) Build Function zip (code only, no dependencies)

Now build a separate zip for only your source code.

```powershell
Set-Location "C:\Users\anilu\Projects\shivaproject"

# Clean old artifacts
if (Test-Path ".\function_build") { Remove-Item ".\function_build" -Recurse -Force }
if (Test-Path ".\aum-report-function.zip") { Remove-Item ".\aum-report-function.zip" -Force }

# Copy only project code package
New-Item -ItemType Directory -Path ".\function_build" | Out-Null
Copy-Item ".\aum_report_pipeline" ".\function_build\aum_report_pipeline" -Recurse

# Remove files not needed in Lambda package
Get-ChildItem ".\function_build" -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force

# Create function zip
Compress-Archive -Path ".\function_build\*" -DestinationPath ".\aum-report-function.zip" -Force

# Show zip size
$sizeMB = (Get-Item ".\aum-report-function.zip").Length / 1MB
Write-Host ("Function zip created: aum-report-function.zip | Size: {0:N2} MB" -f $sizeMB)
```

---

## 7) Attach Layer and Upload Function zip

1. Open your Lambda function.
2. **Code** -> Upload from `.zip` -> upload `aum-report-function.zip`.
3. **Configuration** -> **Layers** -> **Add a layer**.
4. Choose **Custom layers** -> select `aum-report-deps-py312` -> latest version.
5. Save.
6. In **Runtime settings**, set handler:
   - `aum_report_pipeline.lambda_handler.handler`

---

## 8) Runtime and architecture must match

Set Lambda runtime to **Python 3.12**.

Architecture must match what you build for:
- If function architecture is `x86_64` (default), this guide works as-is.
- If function architecture is `arm64`, rebuild layer using arm64-compatible image/wheels.

---

## 9) Test

1. Go to **Test** tab.
2. Use test event:

```json
{}
```

3. Run test.
4. Verify CloudWatch logs for step markers:
   - `PIPELINE_START`
   - `STEP_1_START / STEP_1_SUCCESS`
   - `STEP_3_*`
   - `STEP_4_SUCCESS`
   - `PIPELINE_SUCCESS`

5. Verify output in S3:
- `s3://aris-data-extracts/managers/<ManagerName>/<file>.xlsx`

---

## 10) Update process (very important)

### If only your Python code changes
- Rebuild and upload **function zip only** (`aum-report-function.zip`)
- No new layer version needed

### If dependencies change (`requirements-lambda.txt`)
1. Rebuild `aum-report-deps-layer.zip`
2. Publish **new layer version**
3. Attach new layer version to Lambda
4. Upload function zip if code also changed

---

## 11) Troubleshooting

### Error: `No module named pandas`
Cause: layer missing or wrong folder structure.
Fix:
- Ensure layer zip root contains `python/...`
- Ensure layer is attached to function
- Ensure runtime matches (Python 3.12)

### Error: `Unable to import module ...`
Cause: wrong handler path or zip structure.
Fix:
- Handler must be `aum_report_pipeline.lambda_handler.handler`
- Function zip must include folder `aum_report_pipeline/` at zip root

### Error: Secrets timeout (`secretsmanager... timed out`)
Cause: Lambda networking issue (VPC/NAT/VPC endpoint), not code.
Fix:
- Add NAT or VPC endpoint `com.amazonaws.us-east-1.secretsmanager`

### Error: S3 upload access denied
Cause: IAM policy missing bucket/prefix permissions.
Fix:
- Add `s3:PutObject` on `arn:aws:s3:::aris-data-extracts/managers/*`

---

## 12) Recommended folder artifacts after build

At `C:\Users\anilu\Projects\shivaproject`, you should have:
- `aum-report-deps-layer.zip`
- `aum-report-function.zip`
- `layer_build/` (temporary)
- `function_build/` (temporary)

You can delete `layer_build/` and `function_build/` after successful upload.

---

## 13) Quick checklist before production run

- [ ] Secret `callanOSbilling2` accessible by Lambda role
- [ ] Lambda role has S3 write permission to `aris-data-extracts/managers/*`
- [ ] Handler is `aum_report_pipeline.lambda_handler.handler`
- [ ] Layer attached and runtime matches Python 3.12
- [ ] VPC networking allows access to Secrets Manager and S3
- [ ] Test event `{}` succeeds


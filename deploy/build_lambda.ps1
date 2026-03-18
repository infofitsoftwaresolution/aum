# =============================================================================
# build_lambda.ps1 — Build and deploy the AUM Report Pipeline Lambda package
# =============================================================================
#
# EDIT THESE TWO VARIABLES if needed:
$FUNCTION_NAME   = "aum-report-pipeline"    # Must match your Lambda function name
$AWS_REGION      = "us-east-1"              # Must match your team lead's IAM policy region

$BUILD_DIR       = ".\build"
$PACKAGE_DIR     = "$BUILD_DIR\package"
$ZIP_PATH        = "$BUILD_DIR\aum_lambda.zip"

# =============================================================================
# STEP 1 — Clean and Setup
# =============================================================================
Write-Host "==> Step 1: Cleaning and setting up build directory..." -ForegroundColor Cyan
if (Test-Path $BUILD_DIR) {
    Remove-Item -Recurse -Force $BUILD_DIR -ErrorAction SilentlyContinue
}
# Wait a second for Windows file system to catch up
Start-Sleep -Seconds 1

New-Item -ItemType Directory -Force -Path $PACKAGE_DIR | Out-Null

# Redirect TMP/TEMP to D: drive to avoid "C: drive full" errors
$TEMP_BUILD_DIR = "$BUILD_DIR\tmp"
$PIP_CACHE_DIR  = "$BUILD_DIR\pip_cache"
New-Item -ItemType Directory -Force -Path $TEMP_BUILD_DIR | Out-Null
New-Item -ItemType Directory -Force -Path $PIP_CACHE_DIR | Out-Null

$env:TMP  = (Resolve-Path $TEMP_BUILD_DIR).Path
$env:TEMP = (Resolve-Path $TEMP_BUILD_DIR).Path

# =============================================================================
# STEP 2 — Install dependencies for Amazon Linux 2 (manylinux2014_x86_64)
# =============================================================================
Write-Host "==> Step 2: Installing Lambda-compatible dependencies..." -ForegroundColor Cyan
pip install `
    -r requirements_lambda.txt `
    --target $PACKAGE_DIR `
    --platform manylinux2014_x86_64 `
    --only-binary=:all: `
    --python-version 3.11 `
    --no-cache-dir `
    --upgrade

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: pip install failed. If you see 'PermissionError', close all Explorer windows and try again." -ForegroundColor Red
    exit 1
}

# =============================================================================
# STEP 3 — Copy source code
# =============================================================================
Write-Host "==> Step 3: Copying source code..." -ForegroundColor Cyan
Copy-Item -Recurse -Force ".\aum_report_pipeline" "$PACKAGE_DIR\aum_report_pipeline"

# Remove __pycache__ and .pyc files to keep ZIP clean
Get-ChildItem -Recurse -Path $PACKAGE_DIR -Include "__pycache__" -Directory | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Recurse -Path $PACKAGE_DIR -Include "*.pyc", "*.pyo"          | Remove-Item -Force        -ErrorAction SilentlyContinue

# =============================================================================
# STEP 4 — Create ZIP
# =============================================================================
Write-Host "==> Step 4: Creating deployment ZIP..." -ForegroundColor Cyan
if (Test-Path $ZIP_PATH) { Remove-Item -Force $ZIP_PATH }

if (Get-Command 7z -ErrorAction SilentlyContinue) {
    & 7z a -tzip $ZIP_PATH "$PACKAGE_DIR\*" | Out-Null
} else {
    Compress-Archive -Path "$PACKAGE_DIR\*" -DestinationPath $ZIP_PATH -Force
}

$zipSizeMB = [math]::Round((Get-Item $ZIP_PATH).Length / 1MB, 2)
Write-Host "    ZIP created: $ZIP_PATH ($zipSizeMB MB)" -ForegroundColor Green

if ($zipSizeMB -gt 200) {
    Write-Host "WARNING: ZIP is large (>200 MB). Consider moving more deps to a Lambda Layer." -ForegroundColor Yellow
}

# =============================================================================
# STEP 5 — Deploy to Lambda
# =============================================================================
Write-Host "==> Step 5: Checking AWS credentials and deploying..." -ForegroundColor Cyan

$identity = aws sts get-caller-identity --query "Account" --output text 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: AWS CLI is not authenticated. Run 'aws configure' first." -ForegroundColor Red
    exit 1
}
Write-Host "    Authenticated as AWS Account: $identity" -ForegroundColor Green

aws lambda update-function-code `
    --function-name $FUNCTION_NAME `
    --zip-file "fileb://$ZIP_PATH" `
    --region $AWS_REGION `
    --output table

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Lambda deployment failed. Check function name and region." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "==> DEPLOYMENT COMPLETE!" -ForegroundColor Green
Write-Host "    Function : $FUNCTION_NAME"
Write-Host "    Region   : $AWS_REGION"
Write-Host "    Handler  : aum_report_pipeline.lambda_handler.handler"
Write-Host ""
Write-Host "Next: Go to Lambda Console -> Test tab -> run with {}" -ForegroundColor Yellow

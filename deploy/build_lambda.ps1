# =============================================================================
# build_lambda.ps1 — Build and deploy the AUM Report Pipeline Lambda package
# =============================================================================

$FUNCTION_NAME   = "aum-report-pipeline"    # Your Lambda function name in AWS
$AWS_REGION      = "ap-south-1"             # Must match your .env AWS_REGION
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

# Redirect environment variables to local D: drive to avoid C: drive fullness
$TEMP_BUILD_DIR = "$BUILD_DIR\tmp"
$PIP_CACHE_DIR = "$BUILD_DIR\pip_cache"
New-Item -ItemType Directory -Force -Path $TEMP_BUILD_DIR | Out-Null
New-Item -ItemType Directory -Force -Path $PIP_CACHE_DIR | Out-Null

$env:TMP = (Resolve-Path $TEMP_BUILD_DIR).Path
$env:TEMP = (Resolve-Path $TEMP_BUILD_DIR).Path

# =============================================================================
# STEP 2 — Install dependencies for Amazon Linux 2 (manylinux2014)
# =============================================================================
Write-Host "==> Step 2: Installing Lambda-compatible dependencies..." -ForegroundColor Cyan
# --no-cache-dir helps prevent some lock issues on Windows
pip install `
    -r requirements_lambda.txt `
    --target $PACKAGE_DIR `
    --platform manylinux2014_x86_64 `
    --only-binary=:all: `
    --python-version 3.11 `
    --no-cache-dir `
    --upgrade

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: pip install failed. If you see 'PermissionError', try closing all folders/terminals and run again." -ForegroundColor Red
    exit 1
}

# =============================================================================
# STEP 3 — Copy source code
# =============================================================================
Write-Host "==> Step 3: Copying source code..." -ForegroundColor Cyan
Copy-Item -Recurse -Force ".\aum_report_pipeline" "$PACKAGE_DIR\aum_report_pipeline"

# Clean up build artifacts from the zip
Get-ChildItem -Recurse -Path $PACKAGE_DIR -Include "__pycache__", "*.pyc", "*.pyo" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# =============================================================================
# STEP 4 — Create ZIP
# =============================================================================
Write-Host "==> Step 4: Creating deployment ZIP..." -ForegroundColor Cyan
if (Test-Path $ZIP_PATH) { Remove-Item -Force $ZIP_PATH }

# Use 7-Zip if available for better speed, otherwise standard Compress-Archive
if (Get-Command 7z -ErrorAction SilentlyContinue) {
    & 7z a -tzip $ZIP_PATH "$PACKAGE_DIR\*" | Out-Null
} else {
    Compress-Archive -Path "$PACKAGE_DIR\*" -DestinationPath $ZIP_PATH -Force
}

$zipSizeMB = [math]::Round((Get-Item $ZIP_PATH).Length / 1MB, 2)
Write-Host "    ZIP created: $ZIP_PATH ($zipSizeMB MB)" -ForegroundColor Green

# =============================================================================
# STEP 5 — Deploy
# =============================================================================
Write-Host "==> Step 5: Checking AWS credentials and deploying..." -ForegroundColor Cyan

# Check if logged in
$identity = aws sts get-caller-identity --query "Account" --output text 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: AWS CLI is not logged in or token expired." -ForegroundColor Red
    Write-Host "Please run 'aws sso login' or 'aws configure' first." -ForegroundColor Yellow
    exit 1
}

aws lambda update-function-code `
    --function-name $FUNCTION_NAME `
    --zip-file "fileb://$ZIP_PATH" `
    --region $AWS_REGION `
    --output table

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Lambda deployment failed." -ForegroundColor Red
    exit 1
}

Write-Host "`n==> DEPLOYMENT COMPLETE!" -ForegroundColor Green
Write-Host "    Function : $FUNCTION_NAME"
Write-Host "    Region   : $AWS_REGION"
Write-Host "    Handler  : aum_report_pipeline.lambda_handler.handler"

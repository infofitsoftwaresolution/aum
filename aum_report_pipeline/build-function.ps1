Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Build Lambda function zip with source code only (no dependencies)
# Output: C:\Users\anilu\Projects\shivaproject\aum-report-function.zip

$projectParent = "C:\Users\anilu\Projects\shivaproject"
$projectDir = Join-Path $projectParent "aum_report_pipeline"
$functionBuildDir = Join-Path $projectParent "function_build"
$functionZip = Join-Path $projectParent "aum-report-function.zip"

Set-Location $projectParent

if (!(Test-Path $projectDir)) {
    throw "Project directory not found: $projectDir"
}

if (Test-Path $functionBuildDir) { Remove-Item $functionBuildDir -Recurse -Force }
if (Test-Path $functionZip) { Remove-Item $functionZip -Force }

Write-Host "Building Lambda function zip (code only)..." -ForegroundColor Cyan

New-Item -ItemType Directory -Path $functionBuildDir | Out-Null
Copy-Item $projectDir (Join-Path $functionBuildDir "aum_report_pipeline") -Recurse

# Remove local caches to keep zip smaller
Get-ChildItem $functionBuildDir -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force

Compress-Archive -Path "$functionBuildDir\*" -DestinationPath $functionZip -Force

$sizeMB = (Get-Item $functionZip).Length / 1MB
Write-Host ("Function zip created: {0} ({1:N2} MB)" -f $functionZip, $sizeMB) -ForegroundColor Green
Write-Host "Lambda handler should be: aum_report_pipeline.lambda_handler.handler" -ForegroundColor Yellow


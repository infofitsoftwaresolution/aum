Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Build function zip (code only). Dependencies are packaged in the layer zip.
$projectDir = "D:\shivaproject\shiva2\lambda_s3_to_db"
$buildDir = Join-Path $projectDir "function_build"
$zipPath = Join-Path $projectDir "s3-dat-ingestion-function.zip"

Set-Location $projectDir

if (Test-Path $buildDir) { Remove-Item $buildDir -Recurse -Force }
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

New-Item -ItemType Directory -Path $buildDir | Out-Null

$includeFiles = @(
    "lambda_function.py"
)

foreach ($fileName in $includeFiles) {
    $source = Join-Path $projectDir $fileName
    if (!(Test-Path $source)) {
        throw "Required file not found: $source"
    }
    Copy-Item $source (Join-Path $buildDir $fileName) -Force
}

Compress-Archive -Path "$buildDir\*" -DestinationPath $zipPath -Force

$sizeMB = (Get-Item $zipPath).Length / 1MB
Write-Host ("Function zip created: {0} ({1:N2} MB)" -f $zipPath, $sizeMB) -ForegroundColor Green
Write-Host "Lambda handler: lambda_function.lambda_handler" -ForegroundColor Yellow

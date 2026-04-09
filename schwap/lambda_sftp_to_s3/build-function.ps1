Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Build function zip (code only). Dependencies are packaged in the layer zip.
$projectDir = "D:\shivaproject\schwap\lambda_sftp_to_s3"
$buildDir = Join-Path $projectDir "function_build"
$zipPath = Join-Path $projectDir "schwab-sftp-pull-function.zip"

Set-Location $projectDir

if (Test-Path $buildDir) { Remove-Item $buildDir -Recurse -Force }
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

New-Item -ItemType Directory -Path $buildDir | Out-Null
Copy-Item (Join-Path $projectDir "lambda_function.py") (Join-Path $buildDir "lambda_function.py") -Force

Compress-Archive -Path "$buildDir\*" -DestinationPath $zipPath -Force

$sizeMB = (Get-Item $zipPath).Length / 1MB
Write-Host ("Function zip created: {0} ({1:N2} MB)" -f $zipPath, $sizeMB) -ForegroundColor Green
Write-Host "Lambda handler: lambda_function.lambda_handler" -ForegroundColor Yellow

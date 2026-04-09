Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Build dependency layer zip for Lambda runtime python3.11.
$projectDir = "D:\shivaproject\schwap\lambda_sftp_to_s3"
$layerBuildDir = Join-Path $projectDir "layer_build"
$layerZip = Join-Path $projectDir "schwab-sftp-pull-deps-layer.zip"
$requirementsFile = Join-Path $projectDir "requirements.txt"

Set-Location $projectDir

if (!(Test-Path $requirementsFile)) {
    throw "Requirements file not found: $requirementsFile"
}

if (Test-Path $layerBuildDir) { Remove-Item $layerBuildDir -Recurse -Force }
if (Test-Path $layerZip) { Remove-Item $layerZip -Force }

Write-Host "Building Lambda dependency layer using Docker..." -ForegroundColor Cyan

docker run --rm --entrypoint /bin/bash `
  -v "${PWD}:/var/task" `
  public.ecr.aws/lambda/python:3.11 `
  -lc "set -e; rm -rf /var/task/layer_build; rm -f /var/task/schwab-sftp-pull-deps-layer.zip; mkdir -p /var/task/layer_build/python; pip install -r /var/task/requirements.txt -t /var/task/layer_build/python; python - << 'PY'
import os
import shutil
import zipfile

for root, dirs, _files in os.walk('/var/task/layer_build'):
    for d in list(dirs):
        if d in ('__pycache__', 'tests', 'test'):
            shutil.rmtree(os.path.join(root, d), ignore_errors=True)

zip_path = '/var/task/schwab-sftp-pull-deps-layer.zip'
with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
    for root, _dirs, files in os.walk('/var/task/layer_build/python'):
        for filename in files:
            full_path = os.path.join(root, filename)
            arcname = os.path.relpath(full_path, '/var/task/layer_build').replace('\\\\', '/')
            zf.write(full_path, arcname)

print(f'Created {zip_path}')
PY
"

if (!(Test-Path $layerBuildDir)) {
    throw "Layer build folder not found: $layerBuildDir. Ensure Docker Desktop is running."
}
if (!(Test-Path $layerZip)) {
    throw "Layer zip not found: $layerZip"
}

$sizeMB = (Get-Item $layerZip).Length / 1MB
Write-Host ("Layer zip created: {0} ({1:N2} MB)" -f $layerZip, $sizeMB) -ForegroundColor Green

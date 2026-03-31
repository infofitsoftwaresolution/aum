Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Build Lambda Layer zip with Python dependencies
# Output: C:\Users\anilu\Projects\shivaproject\aum-report-deps-layer.zip

$projectParent = "C:\Users\anilu\Projects\shivaproject"
$projectDir = Join-Path $projectParent "aum_report_pipeline"
$layerBuildDir = Join-Path $projectParent "layer_build"
$layerZip = Join-Path $projectParent "aum-report-deps-layer.zip"

Set-Location $projectParent

if (!(Test-Path $projectDir)) {
    throw "Project directory not found: $projectDir"
}

if (Test-Path $layerBuildDir) { Remove-Item $layerBuildDir -Recurse -Force }
if (Test-Path $layerZip) { Remove-Item $layerZip -Force }

Write-Host "Building Lambda dependency layer using Docker..." -ForegroundColor Cyan

docker run --rm --entrypoint /bin/bash `
  -v "${PWD}:/var/task" `
  public.ecr.aws/lambda/python:3.12 `
  -lc "set -e; rm -rf /var/task/layer_build; rm -f /var/task/aum-report-deps-layer.zip; mkdir -p /var/task/layer_build/python; pip install -r /var/task/aum_report_pipeline/requirements-lambda.txt -t /var/task/layer_build/python; python - << 'PY'
import os
import zipfile

# optional cleanup to reduce package size
for root, dirs, _files in os.walk('/var/task/layer_build'):
    for d in list(dirs):
        if d in ('__pycache__', 'tests'):
            full = os.path.join(root, d)
            try:
                import shutil
                shutil.rmtree(full, ignore_errors=True)
            except Exception:
                pass

zip_path = '/var/task/aum-report-deps-layer.zip'
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
    throw "Layer build folder not found: $layerBuildDir"
}

$sizeMB = (Get-Item $layerZip).Length / 1MB
Write-Host ("Layer zip created: {0} ({1:N2} MB)" -f $layerZip, $sizeMB) -ForegroundColor Green
Write-Host "Next: publish this zip as a Lambda Layer and attach it to your function." -ForegroundColor Yellow


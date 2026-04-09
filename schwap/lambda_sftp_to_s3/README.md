# Schwab SFTP -> S3 Lambda

This Lambda reads SFTP credentials from AWS Secrets Manager secret `schwab_sftp`,
downloads `.zip` files from the SFTP path, and uploads them to S3.

## Secret format (`schwab_sftp`)

Minimum keys required:

```json
{
  "hostname": "sft3.schwab.com",
  "port": 22,
  "username": "your-username",
  "password": "your-password"
}
```

Optional keys:

- `remote_path` (default `"."`)

## Environment variables (optional)

- `SFTP_REMOTE_PATH` - override remote folder path
- `S3_PREFIX` - S3 key prefix, default `Schwab/`

## Build artifacts

From `D:\shivaproject\schwap\lambda_sftp_to_s3`:

```powershell
.\build-function.ps1
.\build-layer.ps1
```

Outputs:

- `schwab-sftp-pull-function.zip`
- `schwab-sftp-pull-deps-layer.zip`

## Lambda settings

- Handler: `lambda_function.lambda_handler`
- Runtime: Python 3.11
- Attach dependency layer built from `schwab-sftp-pull-deps-layer.zip`

IAM permissions required:

- `secretsmanager:GetSecretValue` for secret `schwab_sftp`
- `s3:PutObject` for destination bucket/prefix

## Behavior

On each invocation:

1. Reads secret `schwab_sftp`
2. Connects to SFTP
3. Lists files in the remote path
4. Downloads `.zip` files to `/tmp`
5. Uploads them to hardcoded bucket `s3://callan-sftp/<S3_PREFIX><filename>`

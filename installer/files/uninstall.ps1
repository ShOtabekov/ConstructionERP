<#  Вызывается при удалении программы. Данные (pgdata, data, backups) НЕ удаляются. #>
param([string]$App)
$ErrorActionPreference = "SilentlyContinue"
$SvcExe = Join-Path $App "StroyERP-service.exe"
& $SvcExe stop | Out-Null
& $SvcExe uninstall | Out-Null
schtasks /Delete /F /TN "StroyERP-backup" | Out-Null
schtasks /Delete /F /TN "StroyERP-update" | Out-Null
Stop-Service "StroyERP-PostgreSQL"
$un = Join-Path $App "pgsql\uninstall-postgresql.exe"
if (Test-Path $un) { Start-Process $un -ArgumentList "--mode", "unattended" -Wait }
$wk = Join-Path $App "wkhtmltopdf\uninstall.exe"
if (Test-Path $wk) { Start-Process $wk -ArgumentList "/S" -Wait }

<#  Установка обновления «Строительной ERP».
    - из программы: задача Windows «StroyERP-update» (SYSTEM), пакет из updates\request.json
    - вручную: ярлык «Обновить из файла» (-Pick) — выбрать StroyERP-update-....zip
    Порядок: проверка подписи → резервная копия → замена модулей → обновление базы → запуск.
    При ошибке модули возвращаются как были. #>
param([string]$Package, [switch]$Pick)
$ErrorActionPreference = "Stop"
$App = Split-Path $PSScriptRoot -Parent

if ($Pick) {
    $admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
             ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $admin) {
        Start-Process powershell.exe -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Pick"
        exit
    }
    Add-Type -AssemblyName System.Windows.Forms
    $dlg = New-Object System.Windows.Forms.OpenFileDialog
    $dlg.Filter = "Обновление Строительной ERP (StroyERP-update-*.zip)|*.zip"
    if ($dlg.ShowDialog() -ne "OK") { exit }
    $Package = $dlg.FileName
}

# Дальше запускаются внешние программы: их сообщения в stderr не должны прерывать скрипт
$ErrorActionPreference = "Continue"
$Upd = Join-Path $App "updates"
New-Item -ItemType Directory -Force -Path $Upd, (Join-Path $App "logs") | Out-Null
Start-Transcript -Path (Join-Path $App "logs\update.log") -Append | Out-Null
$Py   = Join-Path $App "python\python.exe"
$Conf = Join-Path $App "odoo.conf"
$Addons = Join-Path $App "addons"
$env:PYTHONUTF8 = "1"

function Status($state, $msg, $ver) {
    $o = [ordered]@{ state = $state; message = $msg; version = $ver; date = (Get-Date -Format "dd.MM.yyyy HH:mm") }
    [IO.File]::WriteAllText((Join-Path $Upd "status.json"), ($o | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
    Write-Host "$state : $msg"
}

if (-not $Package) {
    $req = Join-Path $Upd "request.json"
    if (-not (Test-Path $req)) { Status "error" "Нет файла запроса" ""; exit 1 }
    $Package = (Get-Content -Raw -Encoding UTF8 $req | ConvertFrom-Json).package
    Remove-Item $req -Force
}

$work = Join-Path $Upd "work"
if (Test-Path $work) { Remove-Item $work -Recurse -Force }
New-Item -ItemType Directory -Force -Path $work | Out-Null
$ver = (& $Py (Join-Path $PSScriptRoot "verify_update.py") $Package $Addons $work 2>&1 | Select-Object -Last 1)
if ($LASTEXITCODE -ne 0) { Status "error" "Пакет отклонён: $ver" ""; Stop-Transcript | Out-Null; exit 1 }
$ver = "$ver".Trim()
$old = (Get-Content (Join-Path $App "VERSION") -ErrorAction SilentlyContinue | Select-Object -First 1)
Write-Host "Обновление $old -> $ver"

# 1. Резервная копия (система ещё работает)
& (Join-Path $PSScriptRoot "backup.ps1")

# 2. Остановить, заменить модули
Stop-Service StroyERP -ErrorAction SilentlyContinue
Start-Sleep 3
$keep = Join-Path $App ("backups\addons_{0}_{1}" -f $old, (Get-Date -Format "yyyyMMdd_HHmm"))
Move-Item $Addons $keep -ErrorAction Stop
Move-Item (Join-Path $work "addons") $Addons -ErrorAction Stop

# 3. Обновить базу
$db = ((Get-Content $Conf | Where-Object { $_ -match "^\s*db_name\s*=" }) -replace "^\s*db_name\s*=\s*", "").Trim()
& $Py (Join-Path $App "odoo\odoo-bin") -c $Conf -d $db -u construction_core,construction_sales,construction_finance --stop-after-init
if ($LASTEXITCODE -ne 0) {
    Remove-Item $Addons -Recurse -Force
    Move-Item $keep $Addons
    Start-Service StroyERP
    Status "error" "Ошибка обновления базы, возвращена версия $old (см. logs\update.log)" $old
    Stop-Transcript | Out-Null
    exit 1
}

# 4. Готово
[IO.File]::WriteAllText((Join-Path $App "VERSION"), $ver, (New-Object Text.UTF8Encoding($false)))
Copy-Item (Join-Path $work "update.json") (Join-Path $Upd "installed.json") -Force -ErrorAction SilentlyContinue
Start-Service StroyERP
Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem (Join-Path $App "backups") -Directory -Filter "addons_*" | Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 3 | Remove-Item -Recurse -Force
Status "ok" "Установлена версия $ver" $ver
Stop-Transcript | Out-Null
if ($Pick) { Read-Host "Готово. Нажмите Enter" | Out-Null }

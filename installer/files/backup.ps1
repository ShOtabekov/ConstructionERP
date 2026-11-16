<#  Резервная копия базы в папку backups (zip в формате Odoo: база + файлы).
    Ярлык «Сделать резервную копию» и ежедневная задача в 19:00. Хранятся последние 30 копий. #>
param([switch]$Pause)
$ErrorActionPreference = "Stop"
$App  = Split-Path $PSScriptRoot -Parent
$Conf = Get-Content (Join-Path $App "odoo.conf")
function Opt($k) { ($Conf | Where-Object { $_ -match "^\s*$k\s*=" } | Select-Object -First 1) -replace "^\s*$k\s*=\s*", "" }
$port = Opt "http_port"; $master = Opt "admin_passwd"; $db = Opt "db_name"
$dir  = Join-Path $App "backups"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$out  = Join-Path $dir ("{0}_{1}.zip" -f $db, (Get-Date -Format "yyyy-MM-dd_HHmm"))
try {
    Add-Type -AssemblyName System.Net.Http
    $client = New-Object System.Net.Http.HttpClient
    $client.Timeout = [TimeSpan]::FromMinutes(30)
    $form = New-Object System.Net.Http.MultipartFormDataContent
    $form.Add((New-Object System.Net.Http.StringContent($master)), "master_pwd")
    $form.Add((New-Object System.Net.Http.StringContent($db)), "name")
    $form.Add((New-Object System.Net.Http.StringContent("zip")), "backup_format")
    $resp = $client.PostAsync("http://127.0.0.1:$port/web/database/backup", $form).Result
    if ($resp.Content.Headers.ContentType.MediaType -ne "application/octet-stream") { throw "Odoo вернул ошибку вместо копии" }
    $fs = [IO.File]::Create($out); $resp.Content.CopyToAsync($fs).Wait(); $fs.Close()
    Get-ChildItem $dir -Filter "*.zip" | Sort-Object LastWriteTime -Descending | Select-Object -Skip 30 | Remove-Item -Force
    Write-Host "Копия сохранена: $out" -ForegroundColor Green
    Write-Host "Скопируйте её на флешку, чтобы не потерять данные при поломке компьютера."
}
catch { Write-Host "ОШИБКА: $($_.Exception.Message). Проверьте, что система запущена." -ForegroundColor Red }
if ($Pause) { Read-Host "Нажмите Enter" | Out-Null }

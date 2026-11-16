<#  Восстановление из резервной копии (zip). Текущие данные будут ЗАМЕНЕНЫ. #>
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
$App  = Split-Path $PSScriptRoot -Parent
$Conf = Get-Content (Join-Path $App "odoo.conf")
function Opt($k) { ($Conf | Where-Object { $_ -match "^\s*$k\s*=" } | Select-Object -First 1) -replace "^\s*$k\s*=\s*", "" }
$port = Opt "http_port"; $master = Opt "admin_passwd"; $db = Opt "db_name"
$dlg = New-Object System.Windows.Forms.OpenFileDialog
$dlg.Filter = "Резервная копия (*.zip)|*.zip"
$dlg.InitialDirectory = Join-Path $App "backups"
if ($dlg.ShowDialog() -ne "OK") { exit }
$ans = [System.Windows.Forms.MessageBox]::Show(
    "Все текущие данные будут заменены копией:`n$($dlg.FileName)`n`nПродолжить?",
    "Восстановление", "YesNo", "Warning")
if ($ans -ne "Yes") { exit }
try {
    Add-Type -AssemblyName System.Net.Http
    $client = New-Object System.Net.Http.HttpClient
    $client.Timeout = [TimeSpan]::FromMinutes(30)
    & (Join-Path $PSScriptRoot "backup.ps1")    # на всякий случай — копия текущего состояния
    $f = New-Object System.Net.Http.MultipartFormDataContent
    $f.Add((New-Object System.Net.Http.StringContent($master)), "master_pwd")
    $f.Add((New-Object System.Net.Http.StringContent($db)), "name")
    $client.PostAsync("http://127.0.0.1:$port/web/database/drop", $f).Result | Out-Null
    $f = New-Object System.Net.Http.MultipartFormDataContent
    $f.Add((New-Object System.Net.Http.StringContent($master)), "master_pwd")
    $f.Add((New-Object System.Net.Http.StringContent($db)), "name")
    $f.Add((New-Object System.Net.Http.StringContent("false")), "copy")
    $bytes = New-Object System.Net.Http.ByteArrayContent(,[IO.File]::ReadAllBytes($dlg.FileName))
    $f.Add($bytes, "backup_file", [IO.Path]::GetFileName($dlg.FileName))
    $client.PostAsync("http://127.0.0.1:$port/web/database/restore", $f).Result | Out-Null
    [System.Windows.Forms.MessageBox]::Show("Готово. Данные восстановлены.", "Восстановление") | Out-Null
}
catch { [System.Windows.Forms.MessageBox]::Show("Ошибка: $($_.Exception.Message)", "Восстановление") | Out-Null }

<#  Настройка после копирования файлов (запускается установщиком). Интернет не нужен. #>
param([Parameter(Mandatory = $true)][string]$ParamsFile)
$ErrorActionPreference = "Stop"
$P   = Get-Content -Raw -Encoding UTF8 $ParamsFile | ConvertFrom-Json
$App = $P.app
$Log = Join-Path $App "logs\install.log"
New-Item -ItemType Directory -Force -Path (Join-Path $App "logs"), (Join-Path $App "data"), (Join-Path $App "backups") | Out-Null
Start-Transcript -Path $Log -Append | Out-Null

function Step($n, $t) { Write-Host ""; Write-Host "[$n/7] $t" -ForegroundColor Cyan }
$Py      = Join-Path $App "python\python.exe"
$OdooBin = Join-Path $App "odoo\odoo-bin"
$Conf    = Join-Path $App "odoo.conf"
$PgDir   = Join-Path $App "pgsql"
$PgData  = Join-Path $App "pgdata"
$PgSvc   = "StroyERP-PostgreSQL"
$Db      = "stroyerp"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

function Test-PortBusy([int]$port) {
    [bool](Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
}
function Get-FreePort([int]$start) {
    for ($cand = $start; $cand -lt $start + 50; $cand++) { if (-not (Test-PortBusy $cand)) { return $cand } }
    throw "Нет свободного порта начиная с $start"
}
function Get-ConfValue([string]$key) {
    if (-not (Test-Path $Conf)) { return $null }
    $line = Get-Content $Conf | Where-Object { $_ -match "^\s*$key\s*=" } | Select-Object -First 1
    if ($line) { return ($line -split "=", 2)[1].Trim() }
    return $null
}

try {
    # Порты: другие программы на компьютере могут уже занимать 5433 / 8069
    $pgInstalled = [bool](Get-Service $PgSvc -ErrorAction SilentlyContinue)
    $odooInstalled = [bool](Get-Service StroyERP -ErrorAction SilentlyContinue)
    $oldPg = Get-ConfValue "db_port"; $oldHttp = Get-ConfValue "http_port"
    if ($pgInstalled -and $oldPg) { $P.pg_port = [int]$oldPg }
    elseif (Test-PortBusy ([int]$P.pg_port)) { $P.pg_port = Get-FreePort ([int]$P.pg_port + 1) }
    if ($odooInstalled -and $oldHttp) { $P.http_port = [int]$oldHttp }
    elseif (Test-PortBusy ([int]$P.http_port)) { $P.http_port = Get-FreePort ([int]$P.http_port + 1) }
    # Повторная установка (обновление) поверх рабочей программы: пароли берём из старого odoo.conf
    $Upgrade = $pgInstalled -and (Test-Path $Conf) -and (Get-ConfValue "db_password")
    if ($Upgrade) {
        $P.db_password = Get-ConfValue "db_password"
        $P.master_password = Get-ConfValue "admin_passwd"
        Write-Host "Обновление установленной программы: данные и пароли сохраняются."
        Stop-Service StroyERP -ErrorAction SilentlyContinue
    } elseif ($pgInstalled) {
        throw "Найдена старая база без файла настроек. Удалите программу (Пуск -> StroyERP -> удаление) и установите заново."
    }
    Write-Host "Порт базы: $($P.pg_port), порт программы: $($P.http_port)"
    $UrlFile = Join-Path $App "Строительная ERP.url"
    [IO.File]::WriteAllText($UrlFile, "[InternetShortcut]`r`nURL=http://127.0.0.1:$($P.http_port)/odoo`r`nIconFile=$App\stroyerp.ico`r`nIconIndex=0`r`n", (New-Object Text.UTF8Encoding($false)))

    # ------------------------------------------------------------------ 1
    Step 1 "PostgreSQL (2–5 минут)"
    if (-not $pgInstalled) {
        $pgArgs = @(
            "--mode", "unattended", "--unattendedmodeui", "none",
            "--prefix", "`"$PgDir`"", "--datadir", "`"$PgData`"",
            "--superpassword", $P.pg_super_password,
            "--serverport", $P.pg_port, "--servicename", $PgSvc,
            "--enable-components", "server,commandlinetools",
            "--disable-components", "pgAdmin,stackbuilder",
            "--install_runtimes", "1"
        )
        $pr = Start-Process (Join-Path $App "setup\postgresql-setup.exe") -ArgumentList $pgArgs -Wait -PassThru
        if ($pr.ExitCode -ne 0) { throw "Установка PostgreSQL завершилась с кодом $($pr.ExitCode)" }
    }
    Start-Service $PgSvc -ErrorAction SilentlyContinue
    if ($Upgrade) { $env:PGPASSWORD = $P.db_password; $PgUser = "stroyerp" }
    else { $env:PGPASSWORD = $P.pg_super_password; $PgUser = "postgres" }
    $Psql = Join-Path $PgDir "bin\psql.exe"
    for ($i = 0; $i -lt 30; $i++) {
        & $Psql -h 127.0.0.1 -p $P.pg_port -U $PgUser -d postgres -tAc "select 1" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { break }
        Start-Sleep 2
    }
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL не отвечает на порту $($P.pg_port)" }

    # ------------------------------------------------------------------ 2
    Step 2 "Пользователь базы данных"
    $pw = $P.db_password
    if (-not $Upgrade) {
    & $Psql -h 127.0.0.1 -p $P.pg_port -U postgres -d postgres -v ON_ERROR_STOP=1 -c `
        "DO `$`$BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='stroyerp') THEN CREATE ROLE stroyerp LOGIN CREATEDB PASSWORD '$pw'; ELSE ALTER ROLE stroyerp PASSWORD '$pw'; END IF; END`$`$;"
    if ($LASTEXITCODE -ne 0) { throw "Не удалось создать пользователя базы" }
    }
    Remove-Item Env:PGPASSWORD

    # ------------------------------------------------------------------ 3
    Step 3 "Печать PDF (wkhtmltopdf)"
    $Wk = Join-Path $App "wkhtmltopdf"
    if (-not (Test-Path (Join-Path $Wk "bin\wkhtmltopdf.exe"))) {
        Start-Process (Join-Path $App "setup\wkhtmltox-setup.exe") -ArgumentList "/S", "/D=$Wk" -Wait
    }
    if (-not (Test-Path (Join-Path $Wk "bin\wkhtmltopdf.exe"))) { Write-Warning "wkhtmltopdf не найден — PDF печататься не будет" }

    # ------------------------------------------------------------------ 4
    Step 4 "Файл настроек"
    $confText = @"
[options]
admin_passwd = $($P.master_password)
db_host = 127.0.0.1
db_port = $($P.pg_port)
db_user = stroyerp
db_password = $pw
db_name = $Db
dbfilter = ^$Db`$
addons_path = $App\odoo\odoo\addons,$App\odoo\addons,$App\addons
data_dir = $App\data
logfile = $App\logs\odoo.log
http_interface = 127.0.0.1
http_port = $($P.http_port)
pg_path = $PgDir\bin
bin_path = $Wk\bin
workers = 0
max_cron_threads = 1
without_demo = all
"@
    [IO.File]::WriteAllText($Conf, $confText, (New-Object Text.UTF8Encoding($false)))

    # ------------------------------------------------------------------ 5
    Step 5 "Создание базы и модулей (3–10 минут)"
    $env:PGPASSWORD = $pw
    $exists = & (Join-Path $PgDir "bin\psql.exe") -h 127.0.0.1 -p $P.pg_port -U stroyerp -d postgres -tAc "select 1 from pg_database where datname='$Db'" 2>$null
    if ($exists -ne "1") {
        & $Py $OdooBin -c $Conf -d $Db -i construction_finance --load-language ru_RU --without-demo=all --stop-after-init
        if ($LASTEXITCODE -ne 0) { throw "Odoo не смог создать базу (см. logs\odoo.log)" }
    } else {
        & $Py $OdooBin -c $Conf -d $Db -u construction_core,construction_sales,construction_finance --stop-after-init
    }
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    if ($exists -ne "1") {
        # Новая база: название компании и пароль admin из окна установки.
        # При обновлении не трогаем — у клиента свои данные и пароли.
        $env:ERP_COMPANY = $P.company
        $env:ERP_ADMIN_PASSWORD = $P.admin_password
        Get-Content -Raw -Encoding UTF8 (Join-Path $App "tools\init_company.py") | & $Py $OdooBin shell -c $Conf -d $Db --no-http
        if ($LASTEXITCODE -ne 0) { throw "Не удалось записать данные компании" }
        Remove-Item Env:ERP_ADMIN_PASSWORD
    }

    # ------------------------------------------------------------------ 6
    Step 6 "Служба Windows"
    $SvcExe = Join-Path $App "StroyERP-service.exe"
    $xml = @"
<service>
  <id>StroyERP</id>
  <name>Строительная ERP</name>
  <description>Строительная ERP (Odoo 19) — Actually_team</description>
  <executable>%BASE%\python\python.exe</executable>
  <arguments>"%BASE%\odoo\odoo-bin" -c "%BASE%\odoo.conf"</arguments>
  <workingdirectory>%BASE%</workingdirectory>
  <env name="PYTHONUTF8" value="1"/>
  <depend>$PgSvc</depend>
  <startmode>Automatic</startmode>
  <onfailure action="restart" delay="10 sec"/>
  <log mode="roll-by-size"><sizeThreshold>10240</sizeThreshold><keepFiles>5</keepFiles></log>
  <logpath>%BASE%\logs</logpath>
</service>
"@
    [IO.File]::WriteAllText((Join-Path $App "StroyERP-service.xml"), $xml, (New-Object Text.UTF8Encoding($false)))
    if (-not (Get-Service StroyERP -ErrorAction SilentlyContinue)) { & $SvcExe install | Out-Null }
    & $SvcExe start | Out-Null

    # ------------------------------------------------------------------ 7
    Step 7 "Ежедневная резервная копия и запуск"
    $bk = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$App\tools\backup.ps1`""
    schtasks /Create /F /TN "StroyERP-backup" /SC DAILY /ST 19:00 /RU SYSTEM /TR $bk | Out-Null
    $up = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$App\tools\update.ps1`""
    schtasks /Create /F /TN "StroyERP-update" /SC ONCE /SD 01/01/2020 /ST 00:00 /RU SYSTEM /RL HIGHEST /TR $up | Out-Null
    $url = "http://127.0.0.1:$($P.http_port)/web/login"
    for ($i = 0; $i -lt 60; $i++) {
        try { Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 5 | Out-Null; break } catch { Start-Sleep 3 }
    }
    Start-Process $url
    Remove-Item (Join-Path $App "setup\*.exe") -Force -ErrorAction SilentlyContinue
    Write-Host ""
    if ($Upgrade) { Write-Host "Готово. Программа обновлена, данные и пароли прежние." -ForegroundColor Green }
    else { Write-Host "Готово. Логин: admin, пароль — тот, что вы ввели." -ForegroundColor Green }
    Stop-Transcript | Out-Null
    exit 0
}
catch {
    Write-Host ""
    Write-Host "ОШИБКА: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Журнал: $Log"
    Stop-Transcript | Out-Null
    Start-Sleep 15
    exit 1
}

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

try {
    # ------------------------------------------------------------------ 1
    Step 1 "PostgreSQL (2–5 минут)"
    if (-not (Get-Service $PgSvc -ErrorAction SilentlyContinue)) {
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
    $env:PGPASSWORD = $P.pg_super_password
    $Psql = Join-Path $PgDir "bin\psql.exe"
    for ($i = 0; $i -lt 30; $i++) {
        & $Psql -h 127.0.0.1 -p $P.pg_port -U postgres -d postgres -tAc "select 1" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { break }
        Start-Sleep 2
    }
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL не отвечает на порту $($P.pg_port)" }

    # ------------------------------------------------------------------ 2
    Step 2 "Пользователь базы данных"
    $pw = $P.db_password
    & $Psql -h 127.0.0.1 -p $P.pg_port -U postgres -d postgres -v ON_ERROR_STOP=1 -c `
        "DO `$`$BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='stroyerp') THEN CREATE ROLE stroyerp LOGIN CREATEDB PASSWORD '$pw'; ELSE ALTER ROLE stroyerp PASSWORD '$pw'; END IF; END`$`$;"
    if ($LASTEXITCODE -ne 0) { throw "Не удалось создать пользователя базы" }
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
    $env:ERP_COMPANY = $P.company
    $env:ERP_ADMIN_PASSWORD = $P.admin_password
    Get-Content -Raw -Encoding UTF8 (Join-Path $App "tools\init_company.py") | & $Py $OdooBin shell -c $Conf -d $Db --no-http
    if ($LASTEXITCODE -ne 0) { throw "Не удалось записать данные компании" }
    Remove-Item Env:ERP_ADMIN_PASSWORD

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
    $url = "http://127.0.0.1:$($P.http_port)/web/login"
    for ($i = 0; $i -lt 60; $i++) {
        try { Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 5 | Out-Null; break } catch { Start-Sleep 3 }
    }
    Start-Process $url
    Write-Host ""
    Write-Host "Готово. Логин: admin, пароль — тот, что вы ввели." -ForegroundColor Green
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

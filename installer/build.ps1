<#
  Сборка офлайн-установщика «Строительная ERP».
  Запускать ОДИН РАЗ на компьютере с интернетом (Windows 10/11 x64), из папки installer:
      powershell -ExecutionPolicy Bypass -File build.ps1
  Результат: installer\output\StroyERP-Setup-<версия>.exe — его копируете на флешку,
  у клиента интернет не нужен.
#>
param(
    [string]$OdooSrc   = (Resolve-Path "$PSScriptRoot\..\odoo").Path,
    [string]$AddonsSrc = (Resolve-Path "$PSScriptRoot\..\custom_addons").Path,
    [string]$Version   = (Get-Content "$PSScriptRoot\VERSION" -ErrorAction SilentlyContinue | Select-Object -First 1)
)
$ErrorActionPreference = "Stop"
if (-not $Version) { $Version = "1.0" }
$Version = $Version.Trim()
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ProgressPreference = "SilentlyContinue"

$Here  = $PSScriptRoot
$Dl    = Join-Path $Here "downloads"     # скачанные файлы (кэш, повторно не качаются)
$Stage = Join-Path $Here "stage"         # то, что попадёт в установщик
New-Item -ItemType Directory -Force -Path $Dl, $Stage | Out-Null

# --- что скачиваем (если ссылка устарела — положите файл с этим именем в downloads вручную)
$PY_VER   = "3.12.10"
$PG_FILE  = "postgresql-16-windows-x64.exe"
$Items = @(
  @{ Name = "python-$PY_VER.nupkg";      Url = "https://www.nuget.org/api/v2/package/python/$PY_VER" },
  @{ Name = $PG_FILE;                    Url = "https://get.enterprisedb.com/postgresql/postgresql-16.9-1-windows-x64.exe" },
  @{ Name = "wkhtmltox-0.12.6-1-win64.exe"; Url = "https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6-1/wkhtmltox-0.12.6-1.msvc2015-win64.exe" },
  @{ Name = "WinSW-x64.exe";             Url = "https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe" }
)
$Iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $Iscc)) {
    # несколько адресов: сайт jrsoftware иногда не отдаёт файл скриптам
    $Items += @{ Name = "innosetup-6.exe"; Url = @(
        "https://files.jrsoftware.org/is/6/innosetup-6.4.3.exe",
        "https://github.com/jrsoftware/issrc/releases/download/is-6_4_3/innosetup-6.4.3.exe",
        "https://jrsoftware.org/download.php/is.exe") }
}

function Step($t) { Write-Host ""; Write-Host "==> $t" -ForegroundColor Cyan }

Step "Скачивание компонентов"
foreach ($i in $Items) {
    $dst = Join-Path $Dl $i.Name
    if (Test-Path $dst) { Write-Host "  есть: $($i.Name)"; continue }
    Write-Host "  качаю: $($i.Name)"
    $ok = $false
    foreach ($u in @($i.Url)) {
        try {
            Invoke-WebRequest -Uri $u -OutFile $dst -UseBasicParsing -UserAgent "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" -MaximumRedirection 10
            if ((Get-Item $dst).Length -gt 100KB) { $ok = $true; break }
        } catch { }
        Remove-Item $dst -ErrorAction SilentlyContinue
    }
    if (-not $ok) {
        throw "Не удалось скачать $($i.Name). Скачайте вручную ($(@($i.Url)[-1])) и положите в $Dl с именем $($i.Name)."
    }
}

# Дальше запускаются внешние программы (python, pip, ISCC): их предупреждения в stderr
# не должны останавливать сборку — ошибки проверяем по коду возврата.
$ErrorActionPreference = "Continue"

Step "Python $PY_VER + библиотеки Odoo"
$PyDir = Join-Path $Stage "python"
if (-not (Test-Path "$PyDir\python.exe")) {
    $tmp = Join-Path $env:TEMP "stroyerp_py"
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
    $zip = Join-Path $env:TEMP "stroyerp_python.zip"      # .nupkg — это zip, но Expand-Archive хочет расширение .zip
    Copy-Item (Join-Path $Dl "python-$PY_VER.nupkg") $zip -Force
    Expand-Archive -Path $zip -DestinationPath $tmp -Force
    Remove-Item $zip -Force
    Copy-Item "$tmp\tools" $PyDir -Recurse
    & "$PyDir\python.exe" -m ensurepip --upgrade | Out-Null
}
& "$PyDir\python.exe" -m pip install --upgrade pip wheel setuptools --no-warn-script-location -q
if ($LASTEXITCODE -ne 0) { throw "Не удалось обновить pip" }
& "$PyDir\python.exe" -m pip install -r (Join-Path $OdooSrc "requirements.txt") --no-warn-script-location -q
if ($LASTEXITCODE -ne 0) { throw "pip install завершился с ошибкой" }

Step "Odoo 19 и модули"
$OdooDst = Join-Path $Stage "odoo"
if (Test-Path $OdooDst) { Remove-Item $OdooDst -Recurse -Force }
robocopy $OdooSrc $OdooDst /E /XD .git .github __pycache__ doc debian setup /XF *.pyc /NFL /NDL /NJH /NJS | Out-Null
$AddDst = Join-Path $Stage "addons"
if (Test-Path $AddDst) { Remove-Item $AddDst -Recurse -Force }
robocopy $AddonsSrc $AddDst /E /XD __pycache__ /XF *.pyc /NFL /NDL /NJH /NJS | Out-Null
& "$PyDir\python.exe" -c "import sys; sys.path.insert(0, r'$OdooDst'); import odoo, lxml, psycopg2, PIL, reportlab; print('Python OK')"
if ($LASTEXITCODE -ne 0) { throw "Python не видит библиотеки Odoo" }

Step "Вспомогательные файлы"
Copy-Item (Join-Path $Dl $PG_FILE) (Join-Path $Stage "postgresql-setup.exe") -Force
Copy-Item (Join-Path $Dl "wkhtmltox-0.12.6-1-win64.exe") (Join-Path $Stage "wkhtmltox-setup.exe") -Force
Copy-Item (Join-Path $Dl "WinSW-x64.exe") (Join-Path $Stage "StroyERP-service.exe") -Force
Copy-Item (Join-Path $Here "files\*") $Stage -Recurse -Force
[IO.File]::WriteAllText((Join-Path $Stage "VERSION"), $Version, (New-Object Text.UTF8Encoding($false)))

Step "Inno Setup"
if (-not (Test-Path $Iscc)) {
    Start-Process (Join-Path $Dl "innosetup-6.exe") -ArgumentList "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART" -Wait
}
if (-not (Test-Path $Iscc)) { throw "Inno Setup не установился: $Iscc" }

Step "Сборка установщика"
& $Iscc "/DAppVersion=$Version" "/DStage=$Stage" (Join-Path $Here "StroyERP.iss")
if ($LASTEXITCODE -ne 0) { throw "Ошибка Inno Setup" }
Write-Host ""
Write-Host "Готово: $(Join-Path $Here 'output')" -ForegroundColor Green

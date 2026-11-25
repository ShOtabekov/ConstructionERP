@echo off
chcp 65001 >nul
rem === Вечером перед уходом: копия базы + отправка кода в GitHub ===
rem Odoo должен быть запущен.
set DB=construction_erp_new
set PORT=%1
if "%PORT%"=="" set PORT=8069
set URL=http://127.0.0.1:%PORT%
rem Дома, где установлена StroyERP (8069 занят): backup_db.bat 8070
set /p MASTER=Мастер-пароль Odoo (admin_passwd): 

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmm"') do set D=%%i
set OUT=%USERPROFILE%\Desktop\erp_%DB%_%D%.zip
echo Делаю копию базы %DB% ...
curl -s -X POST -F "master_pwd=%MASTER%" -F "name=%DB%" -F "backup_format=zip" -o "%OUT%" %URL%/web/database/backup
for %%A in ("%OUT%") do if %%~zA LSS 100000 (
  echo ОШИБКА: копия не создана. Проверьте пароль и что Odoo запущен на порту %PORT%.
  echo Если Odoo запущен с --http-port=8070, запускайте: scripts\backup_db.bat 8070
  del "%OUT%" 2>nul
  pause & exit /b 1
)
echo Готово: %OUT%

echo Отправляю код в GitHub ...
cd /d "%~dp0.."
git add -A
git commit -m "работа %D%" >nul 2>&1
git push
echo.
echo Скиньте файл %OUT% на флешку или себе в Telegram.
pause

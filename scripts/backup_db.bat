@echo off
chcp 65001 >nul
rem === Вечером перед уходом: копия базы + отправка кода в GitHub ===
rem Odoo должен быть запущен.
set DB=construction_erp_new
set URL=http://127.0.0.1:8069
set /p MASTER=Мастер-пароль Odoo (admin_passwd): 

set D=%date:~-4%-%date:~3,2%-%date:~0,2%
set OUT=%USERPROFILE%\Desktop\erp_%DB%_%D%.zip
echo Делаю копию базы %DB% ...
curl -s -X POST -F "master_pwd=%MASTER%" -F "name=%DB%" -F "backup_format=zip" -o "%OUT%" %URL%/web/database/backup
for %%A in ("%OUT%") do if %%~zA LSS 100000 (
  echo ОШИБКА: копия не создана. Проверьте имя базы, пароль и что Odoo запущен.
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

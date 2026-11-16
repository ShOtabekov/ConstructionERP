@echo off
chcp 65001 >nul
rem === Дома: перетащите zip-файл копии на этот файл ===
rem Odoo должен быть запущен. Текущая база с этим именем будет ЗАМЕНЕНА.
set DB=construction_erp_new
set URL=http://127.0.0.1:8069
if "%~1"=="" (echo Перетащите zip-файл копии на restore_db.bat & pause & exit /b 1)
set /p MASTER=Мастер-пароль Odoo (admin_passwd): 
echo Внимание: база %DB% на этом компьютере будет заменена копией %~nx1
set /p OK=Продолжить? (да/нет): 
if /i not "%OK%"=="да" exit /b 0

echo Забираю код из GitHub ...
cd /d "%~dp0.."
git pull

echo Удаляю старую базу ...
curl -s -X POST -F "master_pwd=%MASTER%" -F "name=%DB%" %URL%/web/database/drop >nul
echo Восстанавливаю копию (может занять минуту) ...
curl -s -X POST -F "master_pwd=%MASTER%" -F "name=%DB%" -F "copy=false" -F "backup_file=@%~1" %URL%/web/database/restore >nul
echo.
echo Готово. Если меняли код модулей — обновите их (-u construction_core,construction_sales,construction_finance).
pause

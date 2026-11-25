@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0.."
set DB=%1
if "%DB%"=="" set DB=construction_erp_new
echo Будут удалены ВСЕ продажи в базе %DB%: договоры, брони, планы, платежи, ордера, клиенты сделок.
echo Блоки, квартиры, планы, фото и пользователи останутся. Odoo должен быть ОСТАНОВЛЕН.
set /p OK=Сделали копию базы? Напишите ДА и нажмите Enter: 
if /I not "%OK%"=="ДА" if /I not "%OK%"=="DA" (echo Отменено. & pause & exit /b 1)
".venv\Scripts\python.exe" odoo\odoo-bin shell -c config\odoo.conf -d %DB% --no-http < scripts\clean_sales_data.py
pause

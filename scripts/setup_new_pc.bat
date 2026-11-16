@echo off
chcp 65001 >nul
rem === Настройка проекта на новом компьютере (один раз) ===
rem Запускать из папки проекта после git clone. Нужны: Git, Python 3.12, PostgreSQL.
cd /d "%~dp0.."

if not exist odoo\odoo-bin (
  echo Скачиваю Odoo 19 ...
  git clone --depth 1 -b 19.0 https://github.com/odoo/odoo.git odoo || (echo ОШИБКА git clone & pause & exit /b 1)
)
if not exist .venv\Scripts\python.exe (
  echo Создаю окружение Python 3.12 ...
  py -3.12 -m venv .venv || (echo ОШИБКА: нужен Python 3.12 & pause & exit /b 1)
)
echo Устанавливаю библиотеки (5-10 минут) ...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r odoo\requirements.txt || (echo ОШИБКА pip & pause & exit /b 1)

if not exist data mkdir data
if not exist logs mkdir logs
if not exist config mkdir config
if exist config\odoo.conf (echo config\odoo.conf уже есть — не трогаю & goto done)

set PGVER=17
for /d %%D in ("C:\Program Files\PostgreSQL\*") do set PGVER=%%~nxD
set /p DBUSER=Пользователь PostgreSQL [construction_user]: 
if "%DBUSER%"=="" set DBUSER=construction_user
set /p DBPASS=Пароль этого пользователя PostgreSQL: 
set /p MASTER=Мастер-пароль Odoo (как на работе): 
(
echo [options]
echo admin_passwd = %MASTER%
echo db_host = 127.0.0.1
echo db_port = 5432
echo db_user = %DBUSER%
echo db_password = %DBPASS%
echo pg_path = C:\Program Files\PostgreSQL\%PGVER%\bin
echo addons_path = %CD%\odoo\addons,%CD%\custom_addons
echo data_dir = %CD%\data
echo logfile = %CD%\logs\odoo.log
echo http_port = 8069
echo http_interface = 127.0.0.1
echo workers = 0
) > config\odoo.conf
echo Создан config\odoo.conf (PostgreSQL %PGVER%)

:done
echo.
echo Готово. Запуск Odoo:
echo   .venv\Scripts\python.exe odoo\odoo-bin -c config\odoo.conf
echo Потом перетащите zip-копию базы на scripts\restore_db.bat
pause

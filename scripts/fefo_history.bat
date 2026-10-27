@echo off
setlocal
if "%~1"=="" (
    echo Cach dung: fefo_history.bat ^<ma_site^> --mat 10079432 --loc E23 [--date 2026-10-22] [--chi-tiet] [--all] [--out ketqua.txt]
    exit /b 2
)
cd /d "%~dp0.."
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" -m efefo fefo-history --site %*
exit /b %errorlevel%

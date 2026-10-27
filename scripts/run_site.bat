@echo off
setlocal
if "%~1"=="" (
    echo Cach dung: run_site.bat ^<ma_site^> [--interactive]
    exit /b 2
)
cd /d "%~dp0.."
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" -u -m efefo run --site %*
exit /b %errorlevel%

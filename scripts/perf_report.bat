@echo off
setlocal
if "%~1"=="" (
    echo Cach dung: perf_report.bat ^<ma_site^> [--tu 2026-10-01 --den 2026-10-24 --chu-ky 30 --nguong-dut 45 --out file.xlsx]
    exit /b 2
)
cd /d "%~dp0.."
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" -m efefo perf-report --site %*
exit /b %errorlevel%

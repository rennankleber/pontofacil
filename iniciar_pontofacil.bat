@echo off
setlocal
cd /d "%~dp0"

set "PYTHON=python"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import flask, flask_sqlalchemy, flask_login, flask_wtf, reportlab" >nul 2>nul
    if not errorlevel 1 set "PYTHON=%~dp0.venv\Scripts\python.exe"
)

start "" /b powershell.exe -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 3; Start-Process 'http://127.0.0.1:5000'"
"%PYTHON%" "%~dp0run.py"

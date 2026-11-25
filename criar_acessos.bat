@echo off
setlocal
cd /d "%~dp0"

set "PYTHON=python"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import flask, flask_sqlalchemy, flask_login, flask_wtf, reportlab" >nul 2>nul
    if not errorlevel 1 set "PYTHON=%~dp0.venv\Scripts\python.exe"
)

"%PYTHON%" "%~dp0criar_acessos.py"
if errorlevel 1 (
    echo.
    echo O assistente terminou com erro. Leia a mensagem acima.
)
echo.
pause

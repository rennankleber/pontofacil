@echo off
setlocal
cd /d "%~dp0"
set "PONTOFACIL_HOST=0.0.0.0"
set "PONTOFACIL_PORT=5000"

set "PYTHON=python"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import flask, flask_sqlalchemy, flask_login, flask_wtf, reportlab" >nul 2>nul
    if not errorlevel 1 set "PYTHON=%~dp0.venv\Scripts\python.exe"
)

echo O servidor ficara acessivel na rede local. Mantenha esta janela aberta.
echo Enderecos IPv4 deste computador:
ipconfig | findstr /i "IPv4"
echo Em outro dispositivo da mesma rede, abra http://IP_DESTE_COMPUTADOR:5000
echo Nao exponha este servidor de desenvolvimento a internet.
echo.
start "" /b powershell.exe -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 3; Start-Process 'http://127.0.0.1:5000'"
"%PYTHON%" "%~dp0run.py"

@echo off
setlocal
cd /d "%~dp0"
call "%~dp0preparar_ambiente.bat"
if errorlevel 1 (
    pause
    exit /b 1
)

set "PONTOFACIL_HOST=0.0.0.0"
set "PONTOFACIL_PORT=5000"

echo O servidor ficara acessivel na rede local. Mantenha esta janela aberta.
echo Enderecos IPv4 deste computador:
ipconfig | findstr /i "IPv4"
echo Em outro dispositivo da mesma rede, abra http://IP_DESTE_COMPUTADOR:5000
echo Nao exponha este servidor de desenvolvimento a internet.
echo.
start "" /b powershell.exe -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 3; Start-Process 'http://127.0.0.1:5000'"
"%PONTOFACIL_PYTHON%" "%~dp0run.py"
if errorlevel 1 (
    echo.
    echo O servidor terminou com erro. Leia a mensagem acima.
    pause
)

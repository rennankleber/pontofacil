@echo off
setlocal
cd /d "%~dp0"
call "%~dp0preparar_ambiente.bat"
if errorlevel 1 (
    pause
    exit /b 1
)

"%PONTOFACIL_PYTHON%" "%~dp0criar_acessos.py" administrador
if errorlevel 1 (
    echo.
    echo O assistente terminou com erro. Leia a mensagem acima.
)
echo.
pause

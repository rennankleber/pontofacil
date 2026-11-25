@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_INSTALLER=%~dp0python-3.14.10-amd64.exe"
if not exist "%PYTHON_INSTALLER%" (
    echo O instalador python-3.14.10-amd64.exe nao foi encontrado nesta pasta.
    pause
    exit /b 1
)

echo Abrindo o instalador oficial do Python 3.14.10 (64 bits)...
start "" /wait "%PYTHON_INSTALLER%" PrependPath=1 Include_launcher=1
if errorlevel 1 (
    echo A instalacao do Python terminou com erro.
    pause
    exit /b 1
)

echo Python instalado. Feche e abra novamente o CMD antes de iniciar o PontoFacil.
pause

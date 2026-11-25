@echo off
setlocal
cd /d "%~dp0"

set "VENV_DIR=.venv"
set "VENV_PYTHON=%~dp0.venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" (
    "%VENV_PYTHON%" -c "import sys" >nul 2>nul
    if errorlevel 1 goto use_alternate_venv
    goto check_venv
)
if exist ".venv-pontofacil\Scripts\python.exe" goto use_alternate_venv
goto find_python

:use_alternate_venv
set "VENV_DIR=.venv-pontofacil"
set "VENV_PYTHON=%~dp0.venv-pontofacil\Scripts\python.exe"
if exist "%VENV_PYTHON%" goto check_venv
goto find_python

:check_venv
"%VENV_PYTHON%" -c "import sys" >nul 2>nul
if errorlevel 1 (
    echo O ambiente virtual existente nao pode ser iniciado.
    echo Verifique a instalacao do Python e tente novamente.
    endlocal & exit /b 1
)
"%VENV_PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 goto python_version_error
"%VENV_PYTHON%" -c "import flask, flask_sqlalchemy, flask_login, flask_wtf, reportlab" >nul 2>nul
if not errorlevel 1 goto ready

echo As dependencias do projeto ainda nao estao instaladas.
choice /C SN /M "Baixar e instalar em %VENV_DIR% agora? (S/N)"
if errorlevel 2 (
    endlocal & exit /b 1
)
"%VENV_PYTHON%" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo Falha ao instalar as dependencias. Confira sua conexao com a internet.
    endlocal & exit /b 1
)
goto ready

:find_python
set "PYTHON_LAUNCHER="
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if not errorlevel 1 set "PYTHON_LAUNCHER=py -3"
if not defined PYTHON_LAUNCHER (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
    if not errorlevel 1 set "PYTHON_LAUNCHER=python"
)
if not defined PYTHON_LAUNCHER (
    py -3 -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        echo O projeto exige Python 3.10 ou superior.
        endlocal & exit /b 1
    )
    python -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        echo O projeto exige Python 3.10 ou superior.
        endlocal & exit /b 1
    )
    echo Python nao foi encontrado neste computador.
    echo Instale Python 3.10 ou superior em https://www.python.org/downloads/windows/
    echo Durante a instalacao, habilite "Add python.exe to PATH".
    endlocal & exit /b 1
)

echo Criando o ambiente virtual %VENV_DIR%...
%PYTHON_LAUNCHER% -m venv "%VENV_DIR%"
if errorlevel 1 (
    echo Nao foi possivel criar o ambiente virtual.
    endlocal & exit /b 1
)
set "VENV_PYTHON=%~dp0%VENV_DIR%\Scripts\python.exe"
goto check_venv

:python_version_error
echo O ambiente virtual existente exige Python 3.10 ou superior.
if "%VENV_DIR%"==".venv" goto use_alternate_venv
endlocal & exit /b 1

:ready
endlocal & set "PONTOFACIL_PYTHON=%VENV_PYTHON%" & exit /b 0

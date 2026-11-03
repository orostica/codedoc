@echo off
setlocal
set "CODEDOC_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%CODEDOC_PYTHON%" (
    echo Ambiente do CodeDoc ausente. Instale a ferramenta na pasta do CodeDoc. 1>&2
    exit /b 1
)
"%CODEDOC_PYTHON%" -m codedoc.cli %*
exit /b %errorlevel%

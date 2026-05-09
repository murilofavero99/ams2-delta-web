@echo off
REM Captura sessao do iRacing via irsdk e faz upload automatico.
REM Uso: listen_iracing.bat [nome_da_sessao]

set NAME=%1
if "%NAME%"=="" set NAME=iracing_pratica

cd /d "%~dp0backend"
python -m ams2_delta.iracing.listener --name "%NAME%"
pause

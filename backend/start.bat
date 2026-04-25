@echo off
title AMS2 Delta - Backend API

echo ==========================================
echo   AMS2 Delta - Backend API
echo ==========================================
echo.

cd /d "%~dp0"

echo Instalando dependencias...
pip install fastapi uvicorn[standard] pydantic requests --break-system-packages -q

echo.
echo Iniciando servidor FastAPI em http://localhost:8000
echo Documentacao: http://localhost:8000/docs
echo.
echo Pressione Ctrl+C para parar
echo.

set PYTHONPATH=%~dp0..\shared;%PYTHONPATH%
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

pause

@echo off
title AMS2 Delta - Frontend

echo ==========================================
echo   AMS2 Delta - Frontend React
echo ==========================================
echo.

cd /d "%~dp0"

if not exist "node_modules\" (
    echo Instalando dependencias... (primeira vez demora ~1 min)
    npm install
)

echo.
echo Iniciando frontend em http://localhost:5173
echo.
echo Certifique-se que o backend esta rodando em http://localhost:8000
echo Pressione Ctrl+C para parar
echo.

npm run dev

@echo off
setlocal enabledelayedexpansion

REM ═══════════════════════════════════════════════════════════════════
REM   AMS2 Delta Launcher — Abre Terminal com Comandos Prontos
REM ═══════════════════════════════════════════════════════════════════

cls
color 0B

echo.
echo  ╔════════════════════════════════════════════════════════════╗
echo  ║        AMS2 Delta Telemetry Analysis v2.0                  ║
echo  ║              React + FastAPI                               ║
echo  ╚════════════════════════════════════════════════════════════╝
echo.

REM ─── Pega diretório do script ───
set "LAUNCHER_DIR=%~dp0"
set "LAUNCHER_DIR=%LAUNCHER_DIR:~0,-1%"

cd /d "%LAUNCHER_DIR%"

echo  📁 Diretório: %LAUNCHER_DIR%
echo.

REM ─── Verifica pastas ───
if not exist "backend" (
    echo  ❌ Pasta 'backend' não encontrada
    pause
    exit /b 1
)
if not exist "frontend" (
    echo  ❌ Pasta 'frontend' não encontrada
    pause
    exit /b 1
)

echo  ✓ Pastas OK
echo.
echo  🚀 Abrindo terminais...
echo  - Terminal 1: Backend (FastAPI porta 8000)
echo  - Terminal 2: Frontend (React porta 5173)
echo.
echo  Aguarde 10-15 segundos para iniciar completamente...
echo.

REM ─── Terminal Backend ───
start "AMS2 Backend" cmd /k "cd /d "%LAUNCHER_DIR%\backend" && python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000"

timeout /t 2 >nul

REM ─── Terminal Frontend ───
start "AMS2 Frontend" cmd /k "cd /d "%LAUNCHER_DIR%\frontend" && npm run dev"

timeout /t 5 >nul

REM ─── Abre navegador ───
echo.
echo  🌐 Abrindo http://localhost:5173...
timeout /t 2 >nul

REM ─── Tenta abrir com Chrome, Firefox ou Edge ───
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" "http://localhost:5173"
) else if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" (
    start "" "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" "http://localhost:5173"
) else (
    start http://localhost:5173
)

echo.
echo  ✅ Feito! Dois terminais abriram em background.
echo.
echo  ⚠️  Se der erro:
echo     1. Verifique se Python está instalado (python --version)
echo     2. Verifique se Node está instalado (node --version)
echo     3. Rode npm install na pasta frontend
echo.
echo  Este launcher pode ser fechado agora.
echo  Os serviços continuam rodando nos outros terminais.
echo.
timeout /t 5 >nul


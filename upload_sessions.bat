@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ══════════════════════════════════════════════════════════
echo   AMS2 Delta — Upload de Sessões para o Railway
echo ══════════════════════════════════════════════════════════
echo.

:: ─── CONFIGURAÇÃO ───────────────────────────────────────────
:: Coloque aqui a URL do seu backend no Railway (sem / no final)
set "BACKEND_URL=https://ams2-delta-web-production.up.railway.app"

:: Pasta local onde ficam as sessões
set "SESSIONS_FOLDER=backend\sessions"
:: ────────────────────────────────────────────────────────────

:: Verifica se a pasta existe
if not exist "%SESSIONS_FOLDER%" (
    echo [ERRO] Pasta "%SESSIONS_FOLDER%" nao encontrada!
    echo        Rode este script da raiz do projeto ams2-delta-web
    pause
    exit /b 1
)

:: Verifica se curl existe
where curl >nul 2>&1
if errorlevel 1 (
    echo [ERRO] curl nao encontrado. Instale o curl ou use Windows 10+.
    pause
    exit /b 1
)

:: Testa conexão com o backend
echo [INFO] Testando conexao com o backend...
curl -s -o nul -w "%%{http_code}" "%BACKEND_URL%/health" > "%TEMP%\ams2_health.txt" 2>nul
set /p HEALTH_CODE=<"%TEMP%\ams2_health.txt"
del "%TEMP%\ams2_health.txt" 2>nul

if "%HEALTH_CODE%" neq "200" (
    echo [ERRO] Backend nao respondeu. Verifique:
    echo        - URL: %BACKEND_URL%
    echo        - O servico esta rodando no Railway?
    echo        HTTP Status: %HEALTH_CODE%
    pause
    exit /b 1
)
echo [OK] Backend online!
echo.

:: Conta sessões
set COUNT=0
set SUCCESS=0
set FAIL=0

for /d %%D in ("%SESSIONS_FOLDER%\*") do (
    set /a COUNT+=1
)

if %COUNT%==0 (
    echo [AVISO] Nenhuma sessao encontrada em %SESSIONS_FOLDER%
    pause
    exit /b 0
)

echo [INFO] Encontradas %COUNT% sessoes para upload.
echo.

:: Upload de cada sessão
set CURRENT=0
for /d %%D in ("%SESSIONS_FOLDER%\*") do (
    set /a CURRENT+=1
    set "SESSION_ID=%%~nxD"
    set "SESSION_DIR=%%D"

    echo ──────────────────────────────────────────────────────
    echo [!CURRENT!/%COUNT%] Enviando: !SESSION_ID!

    :: Verifica se os dois arquivos existem
    if not exist "!SESSION_DIR!\session.db" (
        echo   [SKIP] session.db nao encontrado
        set /a FAIL+=1
        echo.
        goto :continue_%%D
    )
    if not exist "!SESSION_DIR!\telemetry.parquet" (
        echo   [SKIP] telemetry.parquet nao encontrado
        set /a FAIL+=1
        echo.
        goto :continue_%%D
    )

    :: Mostra tamanho dos arquivos
    for %%F in ("!SESSION_DIR!\session.db") do echo   session.db:          %%~zF bytes
    for %%F in ("!SESSION_DIR!\telemetry.parquet") do echo   telemetry.parquet:   %%~zF bytes

    :: Faz upload via curl
    echo   Enviando...
    curl -s -X POST "%BACKEND_URL%/sessions/upload?session_id=!SESSION_ID!" ^
        -F "session_db=@!SESSION_DIR!\session.db" ^
        -F "telemetry=@!SESSION_DIR!\telemetry.parquet" ^
        -o "%TEMP%\ams2_upload_result.txt" ^
        -w "%%{http_code}" > "%TEMP%\ams2_upload_code.txt" 2>nul

    set /p HTTP_CODE=<"%TEMP%\ams2_upload_code.txt"

    if "!HTTP_CODE!"=="200" (
        echo   [OK] Upload concluido!
        set /a SUCCESS+=1
    ) else (
        echo   [ERRO] HTTP !HTTP_CODE!
        type "%TEMP%\ams2_upload_result.txt" 2>nul
        set /a FAIL+=1
    )

    del "%TEMP%\ams2_upload_result.txt" 2>nul
    del "%TEMP%\ams2_upload_code.txt" 2>nul
    echo.
)

:: Resumo final
echo ══════════════════════════════════════════════════════════
echo   RESULTADO
echo ══════════════════════════════════════════════════════════
echo   Total:     %COUNT%
echo   Sucesso:   %SUCCESS%
echo   Falha:     %FAIL%
echo ══════════════════════════════════════════════════════════
echo.

if %SUCCESS% gtr 0 (
    echo As sessoes ja estao disponiveis no app!
    echo Acesse pelo celular para conferir.
)

echo.
pause

@echo off
setlocal enabledelayedexpansion
title consulta-doc (PROD) :8076

REM ========== 1) Detectar RAIZ del proyecto ==========
for %%I in ("%~dp0") do set "THISDIR=%%~fI"
set "ROOT=%THISDIR%"
if not exist "%ROOT%main.py" (
  echo [ERROR] No encuentro main.py en "%ROOT%".
  pause & exit /b 1
)
pushd "%ROOT%"

REM ========== 2) Config de entorno ==========
set "PORT=8076"
set "NODE_ENV=production"

REM --- SSL ---
set "CERT=C:\Certbot\live\microservicio.codeplex.cloud\fullchain.pem"
set "KEY=C:\Certbot\live\microservicio.codeplex.cloud\privkey.pem"

REM --- CORS (acepta estos dominios + todos los demas via wildcard en FastAPI) ---
set "CORS_ORIGINS=https://microservicio.codeplex.cloud,https://app.codeplex.pe,https://sistema.pseperu.pe,https://dashboardbot.codeplex.pe"

REM ========== 3) Logs ==========
set "LOG_DIR=%ROOT%logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
for /f %%i in ('powershell -NoProfile -Command "(Get-Date).ToString(\"yyyyMMdd\")"') do set YYYYMMDD=%%i
set "LOGFILE=%LOG_DIR%\consulta_doc_%YYYYMMDD%.log"

REM ========== 4) Verificar Python ==========
python --version >nul 2>&1 || (
  echo [ERROR] Python no encontrado en PATH. Instala Python 3.11+.
  popd & pause & exit /b 1
)

REM ========== 5) Verificar certificados SSL ==========
if not exist "%CERT%" (
  echo [ERROR] Certificado no encontrado: %CERT%
  echo         Asegurate de que certbot haya generado los certificados.
  popd & pause & exit /b 1
)
if not exist "%KEY%" (
  echo [ERROR] Clave privada no encontrada: %KEY%
  popd & pause & exit /b 1
)

REM ========== 6) Instalar dependencias si faltan ==========
python -c "import fastapi, uvicorn" >nul 2>&1 || (
  echo [INFO] Instalando dependencias...
  pip install -r requirements.txt -q
)

REM ========== 7) Cerrar instancia anterior en :8076 ==========
for /f "tokens=5" %%p in ('netstat -ano ^| find ":8076" ^| find "LISTENING"') do (
  taskkill /PID %%p /F >nul 2>&1
)
echo [OK] Puerto 8076 liberado.

REM ========== 8) Abrir firewall 8076 ==========
netsh advfirewall firewall add rule name="consulta-doc 8076" dir=in action=allow protocol=TCP localport=8076 >nul 2>&1

REM ========== 9) Lanzar uvicorn con SSL ==========
echo [PROD] Lanzando consulta-doc en https://microservicio.codeplex.cloud:8076 >> "%LOGFILE%"
echo [INFO] Iniciando...

start "" /b cmd /c "python -m uvicorn main:app --host 0.0.0.0 --port %PORT% --ssl-certfile ""%CERT%"" --ssl-keyfile ""%KEY%"" --workers 4 >> ""%LOGFILE%"" 2>&1"

REM ========== 10) Verificar arranque ==========
timeout /t 4 >nul
netstat -ano | find ":%PORT%" | find "LISTENING" >nul || (
  echo [ERROR] Puerto %PORT% no esta escuchando. Revisa el log:
  echo         %LOGFILE%
  popd & pause & exit /b 1
)

echo.
echo [OK]  consulta-doc iniciado en https://microservicio.codeplex.cloud:%PORT%
echo [OK]  Endpoint: GET /Servicios/consultaDocumento/{documento}
echo [LOG] %LOGFILE%
echo.
echo [INFO] Mostrando logs en tiempo real (Ctrl+C para salir)...
powershell -NoProfile -Command "Get-Content -Path '%LOGFILE%' -Wait -Tail 20"

popd
pause
endlocal

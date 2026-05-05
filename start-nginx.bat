@echo off
title nginx reverse proxy :443 → :8076

REM ── 1) Ubicar nginx automáticamente ─────────────────────────────────────
for /f "delims=" %%i in ('where nginx 2^>nul') do set "NGINX_EXE=%%i"

if not defined NGINX_EXE (
    echo [ERROR] nginx no encontrado en el PATH del sistema.
    echo         Instala nginx y asegurate de que este en el PATH.
    pause & exit /b 1
)

echo [INFO] nginx encontrado en: %NGINX_EXE%

REM ── Obtener directorio de nginx ───────────────────────────────────────────
for %%i in ("%NGINX_EXE%") do set "NGINX_DIR=%%~dpi"
set "NGINX_CONF=%NGINX_DIR%conf\nginx.conf"

REM ── Crear carpetas temp necesarias ───────────────────────────────────────
mkdir "%NGINX_DIR%temp\client_body_temp" 2>nul
mkdir "%NGINX_DIR%temp\proxy_temp"       2>nul
mkdir "%NGINX_DIR%temp\fastcgi_temp"     2>nul
mkdir "%NGINX_DIR%temp\uwsgi_temp"       2>nul
mkdir "%NGINX_DIR%temp\scgi_temp"        2>nul
mkdir "%NGINX_DIR%logs"                  2>nul

REM ── 2) Copiar nginx.conf al directorio de nginx ──────────────────────────
mkdir "C:\go\consulta-doc\conf" 2>nul
copy /Y "%~dp0nginx.conf" "%NGINX_CONF%" >nul
echo [OK] nginx.conf copiado.

REM ── 3) Abrir puerto 443 en el firewall ───────────────────────────────────
netsh advfirewall firewall add rule name="nginx 443" dir=in action=allow protocol=TCP localport=443 >nul 2>&1
echo [OK] Firewall 443 abierto.

REM ── 4) Detener instancia anterior si existe ───────────────────────────────
taskkill /IM nginx.exe /F >nul 2>&1
timeout /t 1 >nul

REM ── 5) Iniciar nginx con config explícita ────────────────────────────────
start "" /b "%NGINX_EXE%" -c "%NGINX_CONF%"
timeout /t 2 >nul

tasklist | find /I "nginx.exe" >nul
if errorlevel 1 (
    echo [ERROR] nginx no inicio. Revisa C:\nginx\logs\error.log
    pause & exit /b 1
)

echo.
echo [OK] nginx corriendo — https://microservicio.codeplex.cloud → localhost:8076
echo [OK] Prueba: https://microservicio.codeplex.cloud/Servicios/consultaDocumento/20612547948
echo.
pause

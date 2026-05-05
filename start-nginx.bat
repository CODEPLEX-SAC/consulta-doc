@echo off
title nginx reverse proxy :443 → :8076

REM ── 1) Ubicar nginx ──────────────────────────────────────────────────────
set "NGINX_EXE=C:\go\consulta-doc\nginx.exe"
set "NGINX_CONF=C:\go\consulta-doc\conf\nginx.conf"

if not exist "%NGINX_EXE%" (
    echo [ERROR] No se encontro nginx en C:\go\consulta-doc\
    pause & exit /b 1
)

REM ── Crear carpetas temp necesarias ───────────────────────────────────────
mkdir "C:\go\consulta-doc\temp\client_body_temp" 2>nul
mkdir "C:\go\consulta-doc\temp\proxy_temp"       2>nul
mkdir "C:\go\consulta-doc\temp\fastcgi_temp"     2>nul
mkdir "C:\go\consulta-doc\temp\uwsgi_temp"       2>nul
mkdir "C:\go\consulta-doc\temp\scgi_temp"        2>nul
mkdir "C:\go\consulta-doc\logs"                  2>nul

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

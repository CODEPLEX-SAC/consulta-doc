@echo off
title nginx reverse proxy :443 → :8076

set "NGINX_EXE=C:\nginx\nginx.exe"
set "NGINX_CONF=C:\nginx\conf\nginx.conf"

if not exist "%NGINX_EXE%" (
    echo [ERROR] No se encontro C:\nginx\nginx.exe
    pause & exit /b 1
)

REM ── Crear carpetas necesarias ─────────────────────────────────────────────
mkdir "C:\nginx\temp\client_body_temp" 2>nul
mkdir "C:\nginx\temp\proxy_temp"       2>nul
mkdir "C:\nginx\temp\fastcgi_temp"     2>nul
mkdir "C:\nginx\temp\uwsgi_temp"       2>nul
mkdir "C:\nginx\temp\scgi_temp"        2>nul
mkdir "C:\nginx\logs"                  2>nul

REM ── Copiar nginx.conf ─────────────────────────────────────────────────────
copy /Y "%~dp0nginx.conf" "%NGINX_CONF%" >nul
echo [OK] nginx.conf copiado.

REM ── Abrir firewall ────────────────────────────────────────────────────────
netsh advfirewall firewall add rule name="nginx 443" dir=in action=allow protocol=TCP localport=443 >nul 2>&1
echo [OK] Firewall 443 abierto.

REM ── Detener instancia anterior ────────────────────────────────────────────
taskkill /IM nginx.exe /F >nul 2>&1
timeout /t 1 >nul

REM ── Iniciar nginx ─────────────────────────────────────────────────────────
cd /d "C:\nginx"
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

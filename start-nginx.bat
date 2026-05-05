@echo off
title nginx reverse proxy :443 → :8076

REM ── 1) Ubicar nginx ──────────────────────────────────────────────────────
set "NGINX=C:\nginx\nginx.exe"
if not exist "%NGINX%" (
    echo [ERROR] No se encontro nginx en C:\nginx\
    echo         Descargalo de https://nginx.org/en/download.html
    echo         y extrae el contenido en C:\nginx\
    pause & exit /b 1
)

REM ── 2) Copiar nginx.conf al directorio de nginx ──────────────────────────
copy /Y "%~dp0nginx.conf" "C:\nginx\conf\nginx.conf" >nul
echo [OK] nginx.conf copiado.

REM ── 3) Abrir puerto 443 en el firewall ───────────────────────────────────
netsh advfirewall firewall add rule name="nginx 443" dir=in action=allow protocol=TCP localport=443 >nul 2>&1
echo [OK] Firewall 443 abierto.

REM ── 4) Detener instancia anterior si existe ───────────────────────────────
taskkill /IM nginx.exe /F >nul 2>&1

REM ── 5) Iniciar nginx ─────────────────────────────────────────────────────
start "" /b "%NGINX%"
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

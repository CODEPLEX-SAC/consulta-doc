#!/bin/bash
export PYTHONIOENCODING=utf-8

echo ""
echo "╔════════════════════════════════════════════════════════╗"
echo "║       consulta-doc — Script de ejecución Mac/Linux    ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

PORT=8076
export NODE_ENV="${NODE_ENV:-development}"
export CORS_ORIGINS="https://microservicio.codeplex.cloud,https://app.codeplex.pe,https://sistema.pseperu.pe,https://dashboardbot.codeplex.pe"

CERT="${CERT:-/etc/letsencrypt/live/microservicio.codeplex.cloud/fullchain.pem}"
KEY="${KEY:-/etc/letsencrypt/live/microservicio.codeplex.cloud/privkey.pem}"

PID=$(lsof -ti :$PORT 2>/dev/null)
if [ ! -z "$PID" ]; then
    kill -9 $PID 2>/dev/null
    echo "✓ Puerto $PORT liberado"
fi

python3 -c "import fastapi" 2>/dev/null || {
    echo "Instalando dependencias..."
    pip3 install -r requirements.txt -q
}

if [ -f "$CERT" ] && [ -f "$KEY" ]; then
    export CERT="$CERT"
    export KEY="$KEY"
    SSL_ARGS="--ssl-certfile $CERT --ssl-keyfile $KEY"
    PROTO="https"
    echo "✓ SSL activado: $CERT"
else
    SSL_ARGS=""
    PROTO="http"
    echo "⚠  SSL no disponible (certificados no encontrados) — modo HTTP"
fi

echo ""
echo "  Endpoint: GET /Servicios/consultaDocumento/{documento}"
echo "  URL:      $PROTO://localhost:$PORT"
echo "  Swagger:  $PROTO://localhost:$PORT/docs"
echo "  Entorno:  $NODE_ENV"
echo ""
echo "════════════════════════════════════════════════════════"
echo ""

uvicorn main:app \
    --reload \
    --host 0.0.0.0 \
    --port $PORT \
    $SSL_ARGS

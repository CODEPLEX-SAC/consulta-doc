#!/usr/bin/env bash
# Dispara el refresh manual de los padrones SUNAT.
# Uso: ./scripts/manual_refresh.sh [ruc|local_anexo]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

TIPO="${1:-}"
if [ -n "$TIPO" ]; then
    python3 jobs/refresh_padrones.py "$TIPO"
else
    python3 jobs/refresh_padrones.py ruc local_anexo
fi

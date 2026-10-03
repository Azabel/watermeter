#!/usr/bin/env bash
set -e

# Primera ejecución: calibración inicial incluida en la imagen (se puede
# rehacer desde la web). No se pisa una calibración ya guardada.
if [ ! -f /data/calibration.json ] && [ -f /app/config/calibration.json ]; then
    cp /app/config/calibration.json /data/calibration.json
fi

echo "Iniciando watermeter (add-on)..."
exec /opt/venv/bin/python -m watermeter --addon

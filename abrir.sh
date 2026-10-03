#!/usr/bin/env bash
# SJR-Geo — abre o aplicativo servido por HTTP (ver ABRIR.bat para o porquê).
cd "$(dirname "$0")"
if [ ! -f data/processados/zoneamento.geojson ]; then
  echo "Os dados ainda nao foram gerados. Rode: python pipeline/run_all.py"; exit 1
fi
echo "SJR-Geo — http://localhost:8080/web/  (Ctrl+C encerra)"
(sleep 1 && (xdg-open http://localhost:8080/web/ 2>/dev/null || open http://localhost:8080/web/ 2>/dev/null)) &
python -m http.server 8080

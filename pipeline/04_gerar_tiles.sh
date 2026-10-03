#!/usr/bin/env bash
# Gera tiles vetoriais PMTiles a partir dos GeoJSON processados.
# Requer tippecanoe >= 2.17 (https://github.com/felt/tippecanoe)
#   Ubuntu/WSL: git clone https://github.com/felt/tippecanoe && cd tippecanoe \
#               && make -j && sudo make install
#
# Rode antes:  python pipeline/run_all.py --completo
# (o --completo gera edificacoes_municipio.geojson com os 110 mil predios;
#  sem ele so existe o recorte do nucleo urbano)
#
# Hospedagem: qualquer storage estatico (GitHub Pages, Cloudflare R2/Pages).
# PMTiles usa range requests — sem servidor de tiles, custo ~zero.
set -euo pipefail
cd "$(dirname "$0")/../data/processados"

EDIF=edificacoes.geojson
[ -f edificacoes_municipio.geojson ] && EDIF=edificacoes_municipio.geojson
echo "edificacoes: $EDIF"

# Duas passadas com faixas de zoom diferentes, unidas no fim com tile-join.
# tippecanoe aplica -z/-Z a TODAS as camadas da invocacao, entao nao da para
# usar uma unica chamada: o zoneamento precisa existir desde o zoom baixo e
# sem descarte (sao 44 poligonos, e a consulta depende de todos), enquanto
# edificacoes e enderecos so fazem sentido de perto.

tippecanoe -o /tmp/sjr_base.pmtiles --force \
  -Z8 -z15 --no-tile-size-limit --no-feature-limit \
  -L zoneamento:zoneamento.geojson \
  -L vias:vias.geojson

tippecanoe -o /tmp/sjr_detalhe.pmtiles --force \
  -Z13 -z16 --drop-densest-as-needed --extend-zooms-if-still-dropping \
  -L "edificacoes:$EDIF" \
  -L enderecos:enderecos.geojson

tile-join -o sjr.pmtiles --force /tmp/sjr_base.pmtiles /tmp/sjr_detalhe.pmtiles
rm -f /tmp/sjr_base.pmtiles /tmp/sjr_detalhe.pmtiles

ls -lh sjr.pmtiles
echo "ok -> data/processados/sjr.pmtiles"
echo
echo "Agora, em web/index.html, troque os sources GeoJSON pelo bloco PMTiles"
echo "comentado no fim do arquivo e reative o <script> do pmtiles.js."

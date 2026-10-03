"""
Enderecos do CNEFE 2022 (IBGE) — Cadastro Nacional de Enderecos para Fins
Estatisticos, municipio 2111201.

Entrada : SIG/2111201.csv                          (118.456 pontos)
          (equivalente aos shapefiles DOMICILIOS_SAO_JOSE_DE_RIBAMAR.shp e
           RIBAMAR_LOTES.shp, que sao o MESMO dado — ver README)
Saida   : data/processados/enderecos.json          (municipio inteiro, compacto)
          data/processados/stats_enderecos.json    (agregado por zona)

Por que isso importa: nao existe cadastro imobiliario georreferenciado de
Sao Jose de Ribamar. O CNEFE e o substituto viavel — nao da o poligono do
lote, mas da a contagem de domicilios e estabelecimentos por zona, que
sustenta a consulta em nivel de zona e as estatisticas do painel.

ANTES este script recortava os pontos num bbox de 0,08 grau em torno da sede
e exportava 17 mil dos 118 mil. Com o app abrindo no municipio inteiro, o
corte ficou visivel do pior jeito: metade oeste sem ponto nenhum, enquanto o
painel somava os 118 mil. Mapa e numero tem de contar a mesma historia, entao
exportamos tudo e economizamos no PESO DE CADA PONTO, nao na quantidade.

Dai o formato COMPACTO, e nao GeoJSON: num FeatureCollection de pontos, 60%
dos bytes sao "type":"Feature" / "properties" / "geometry" / "coordinates"
repetidos 118 mil vezes. Aqui cada ponto e uma tupla [lon, lat, especie,
indice_da_zona] e o cliente monta o FeatureCollection uma vez, ao carregar
(ver expandeEnderecos em web/index.html).
   - 123 bytes por ponto em GeoJSON -> ~26 no formato compacto;
   - 'especie_nome' saiu: deriva de 'especie', e a tabela vai uma vez so;
   - coordenada com 5 casas (~1,1 m), mais precisao do que o CNEFE tem.
"""
import csv
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_geo import PolygonIndex, write_json

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SRC = os.path.join(BASE, "SIG", "2111201.csv")
PROC = os.path.join(BASE, "data", "processados")

# Tabela de especie do CNEFE 2022 (IBGE)
ESPECIE = {
    1: "Domicilio particular",
    2: "Domicilio coletivo",
    3: "Estabelecimento agropecuario",
    4: "Estabelecimento de ensino",
    5: "Estabelecimento de saude",
    6: "Estabelecimento de outras finalidades",
    7: "Edificacao em construcao ou reforma",
    8: "Estabelecimento religioso",
}
DOMICILIOS = {1, 2}


def main():
    print("ENDERECOS (CNEFE 2022)")
    if not os.path.exists(SRC):
        sys.exit(f"ERRO: nao encontrei {SRC}")
    zpath = os.path.join(PROC, "zoneamento.geojson")
    if not os.path.exists(zpath):
        sys.exit("ERRO: rode 10_zoneamento.py antes (preciso das zonas)")

    with open(zpath, encoding="utf-8") as f:
        zonas = json.load(f)["features"]
    idx = PolygonIndex(zonas)

    stats = defaultdict(lambda: defaultdict(int))
    # a sigla da zona vira indice: repetir "ZEU" 118 mil vezes custa 5 bytes
    # cada; o indice custa 1
    zonas_ord, idx_zona = [], {}
    pontos, fora, total = [], 0, 0
    especies_vistas = defaultdict(int)

    with open(SRC, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f, delimiter=";")
        for row in r:
            total += 1
            try:
                lat = float(row["LATITUDE"])
                lon = float(row["LONGITUDE"])
                esp = int(row["COD_ESPECIE"])
            except (TypeError, ValueError, KeyError):
                continue
            especies_vistas[esp] += 1
            k = idx.find(lon, lat)
            if k is None:
                fora += 1
                continue
            sigla = zonas[k]["properties"]["sigla"]
            s = stats[sigla]
            s["total"] += 1
            s[f"esp_{esp}"] += 1
            if esp in DOMICILIOS:
                s["domicilios"] += 1

            if sigla not in idx_zona:
                idx_zona[sigla] = len(zonas_ord)
                zonas_ord.append(sigla)
            pontos.append([round(lon, 5), round(lat, 5), esp, idx_zona[sigla]])

    write_json(os.path.join(PROC, "enderecos.json"), {
        "formato": "compacto-v1",
        "campos": ["lon", "lat", "especie", "zona_idx"],
        "especies": ESPECIE,
        "zonas": zonas_ord,
        "n": len(pontos),
        "pontos": pontos,
    }, compacto=True)
    write_json(os.path.join(PROC, "stats_enderecos.json"),
               {"especies": ESPECIE,
                "por_zona": {k: dict(v) for k, v in sorted(stats.items())}})

    print(f"  linhas lidas: {total:,}")
    print(f"  fora das zonas: {fora:,}")
    print(f"  dentro das zonas: {total - fora:,}")
    print(f"  exportados para o mapa: {len(pontos):,} "
          f"({100*len(pontos)/max(1,total-fora):.1f}% dos que caem em zona)")
    print("  especies presentes:")
    for e, n in sorted(especies_vistas.items()):
        print(f"    {e} {ESPECIE.get(e, '?'):<40} {n:>7,}")
    print("  top 8 zonas por domicilios:")
    for k, v in sorted(stats.items(), key=lambda kv: -kv[1]["domicilios"])[:8]:
        print(f"    {k:<18} {v['domicilios']:>7,} domicilios "
              f"({v['total']:,} enderecos)")


if __name__ == "__main__":
    main()

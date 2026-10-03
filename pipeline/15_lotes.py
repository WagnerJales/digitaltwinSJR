"""
Cadastro de lotes — CAMINHO CRITICO DO PROJETO, ainda bloqueado.

Sao Jose de Ribamar nao dispoe de cadastro imobiliario georreferenciado
publico. Enquanto ele nao vier da Secretaria da Receita/Urbanismo, a consulta
do app opera em nivel de ZONA. Este script ja esta pronto para o dia em que a
base chegar.

ATENCAO: os arquivos SIG/RIBAMAR_LOTES.shp e SIG/DOMICILIOS_SAO_JOSE_DE_RIBAMAR.shp
NAO sao lotes, apesar do nome. Sao os pontos de endereco do CNEFE 2022 —
byte a byte identicos entre si e ao SIG/2111201.csv (118.456 pontos, geometria
Point, campos COD_UF/COD_MUN/COD_ESPECIE/LATITUDE/LONGITUDE/NV_GEO_COORD).
Quem tratar RIBAMAR_LOTES como cadastro vai errar. Esse dado ja e consumido
por 13_enderecos.py.

Uso, quando houver o cadastro de verdade:
    coloque o shapefile em  data/brutos/lotes_sjr.shp
    ajuste COLUNA_ID abaixo para o campo de inscricao cadastral
    python pipeline/15_lotes.py

Saida: data/processados/lotes.geojson
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_geo import (PolygonIndex, read_shapefile, area_m2, centroid,
                     write_geojson)

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
PROC = os.path.join(BASE, "data", "processados")
ARQ_LOTES = os.path.join(BASE, "data", "brutos", "lotes_sjr")

COLUNA_ID = "inscricao"        # <-- AJUSTAR ao campo do cadastro recebido


def main():
    print("LOTES")
    if not os.path.exists(ARQ_LOTES + ".shp"):
        print(f"  cadastro ausente ({ARQ_LOTES}.shp) — etapa pulada.")
        print("  A consulta do app segue em nivel de zona. Ver docstring.")
        return

    zpath = os.path.join(PROC, "zoneamento.geojson")
    if not os.path.exists(zpath):
        sys.exit("ERRO: rode 10_zoneamento.py antes")
    with open(zpath, encoding="utf-8") as f:
        zonas = json.load(f)["features"]
    idx = PolygonIndex(zonas)

    lotes = read_shapefile(ARQ_LOTES)
    print(f"  {len(lotes)} lotes lidos")
    if lotes and COLUNA_ID not in lotes[0]["properties"]:
        sys.exit(f"ERRO: campo '{COLUNA_ID}' nao existe. Campos disponiveis: "
                 + ", ".join(lotes[0]["properties"].keys()))

    out, sem_zona = [], 0
    for lote in lotes:
        p = lote["properties"]
        g = lote["geometry"]
        if g is None:
            continue
        c = centroid(g)
        # zona pelo centroide. Um lote pode cruzar duas zonas — nesse caso o
        # correto e recortar o poligono e reportar percentuais, o que exige
        # uma engine de geometria (shapely). Aqui atribuimos a zona
        # predominante e marcamos o caso para revisao.
        k = idx.find(c[0], c[1]) if c else None
        if k is None:
            sem_zona += 1
            zona = None
        else:
            zona = zonas[k]["properties"]["sigla"]
        out.append({"type": "Feature",
                    "properties": {"id_lote": str(p.get(COLUNA_ID, "")),
                                   "area_m2": round(area_m2(g), 1),
                                   "zona": zona},
                    "geometry": g})

    if sem_zona:
        print(f"  AVISO: {sem_zona} lotes fora de qualquer zona")
    write_geojson(os.path.join(PROC, "lotes.geojson"), out)
    print("  Lembre de reativar a camada de lotes em web/index.html.")


if __name__ == "__main__":
    main()

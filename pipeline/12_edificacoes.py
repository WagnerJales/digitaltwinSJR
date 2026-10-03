"""
Edificacoes (footprints) do Google Open Buildings v3.

Entrada : SIG/07f_buildings.csv   (~520 MB, 2,08 milhoes de predios; o tile 07f
                                   cobre bem mais que Sao Jose de Ribamar)
Saida   : data/processados/edificacoes.geojson       (recorte do nucleo urbano)
          data/processados/stats_edificacoes.json    (agregado por zona)
          data/processados/edificacoes_municipio.geojson  (opcional, --completo)

O arquivo e grande demais para carregar em memoria, entao o processamento e
em streaming: uma unica passada, atribuindo zona pelo centroide (que ja vem
como coluna no CSV) e materializando a geometria apenas para os predios que
entram no recorte de saida.

LIMITACAO IMPORTANTE: o Open Buildings v3 NAO fornece altura. Nao inventamos
altura nenhuma — o app extruda todos os predios numa altura nominal e rotula
a camada como footprint. Quem quiser 3D real precisa de LiDAR, do Open
Buildings 2.5D Temporal ou do cadastro da Prefeitura.
"""
import csv
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_geo import (PolygonIndex, wkt_polygon, write_json)

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SRC = os.path.join(BASE, "SIG", "07f_buildings.csv")
PROC = os.path.join(BASE, "data", "processados")

# Recorte do nucleo urbano para a demo no navegador. Um GeoJSON com os 332 mil
# predios do municipio inteiro passaria de 250 MB e travaria o MapLibre —
# para o municipio todo use --completo + tippecanoe (pipeline/04_gerar_tiles.sh).
DEMO_BBOX = (-44.0950, -2.5950, -44.0150, -2.5150)

CONF_MIN = 0.70          # confianca minima do detector
AREA_MIN = 15.0          # m2 — abaixo disso e ruido/telheiro


def main(completo=False):
    print("EDIFICACOES (Google Open Buildings v3)")
    if not os.path.exists(SRC):
        sys.exit(f"ERRO: nao encontrei {SRC}")
    zpath = os.path.join(PROC, "zoneamento.geojson")
    if not os.path.exists(zpath):
        sys.exit("ERRO: rode 10_zoneamento.py antes (preciso das zonas)")

    with open(zpath, encoding="utf-8") as f:
        zonas = json.load(f)["features"]
    idx = PolygonIndex(zonas)
    print(f"  indice de {len(zonas)} zonas construido")

    stats = defaultdict(lambda: {"n": 0, "area_m2": 0.0})
    demo, fora_zona, total, descartadas = [], 0, 0, 0

    saida_mun = None
    if completo:
        p = os.path.join(PROC, "edificacoes_municipio.geojson")
        saida_mun = open(p, "w", encoding="utf-8")
        saida_mun.write('{"type":"FeatureCollection","features":[')
        primeiro = [True]

    csv.field_size_limit(10 ** 7)
    with open(SRC, newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        next(r)
        for row in r:
            total += 1
            if total % 500_000 == 0:
                print(f"  ...{total:,} linhas | {sum(s['n'] for s in stats.values()):,} "
                      f"em zonas | {len(demo):,} no recorte demo", flush=True)
            conf = float(row[3])
            area = float(row[2])
            if conf < CONF_MIN or area < AREA_MIN:
                descartadas += 1
                continue
            lat, lon = float(row[0]), float(row[1])
            k = idx.find(lon, lat)
            if k is None:
                fora_zona += 1
                continue
            sigla = zonas[k]["properties"]["sigla"]
            s = stats[sigla]
            s["n"] += 1
            s["area_m2"] += area

            no_demo = (DEMO_BBOX[0] <= lon <= DEMO_BBOX[2]
                       and DEMO_BBOX[1] <= lat <= DEMO_BBOX[3])
            if not (no_demo or completo):
                continue
            geom = wkt_polygon(row[4])
            if geom is None:
                continue
            feat = {"type": "Feature",
                    "properties": {"area_m2": round(area, 1),
                                   "confianca": round(conf, 2),
                                   "zona": sigla},
                    "geometry": geom}
            if no_demo:
                demo.append(feat)
            if completo:
                if not primeiro[0]:
                    saida_mun.write(",")
                primeiro[0] = False
                json.dump(feat, saida_mun, ensure_ascii=False,
                          separators=(",", ":"))

    if saida_mun:
        saida_mun.write("]}")
        saida_mun.close()
        p = os.path.join(PROC, "edificacoes_municipio.geojson")
        print(f"  -> edificacoes_municipio.geojson: {os.path.getsize(p)/1e6:.0f} MB "
              f"(para tippecanoe, nao para o navegador)")

    os.makedirs(PROC, exist_ok=True)
    out = os.path.join(PROC, "edificacoes.geojson")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": demo}, f,
                  ensure_ascii=False, separators=(",", ":"))
    print(f"  -> edificacoes.geojson: {len(demo):,} feicoes, "
          f"{os.path.getsize(out)/1e6:.1f} MB (recorte do nucleo urbano)")

    dentro = sum(s["n"] for s in stats.values())

    # O bbox do recorte vai para o cliente: e ele que permite desenhar onde os
    # dados terminam. Constante duplicada no JS acabaria divergindo daqui.
    write_json(os.path.join(PROC, "stats_edificacoes.json"),
               {"recorte": {
                    "bbox": list(DEMO_BBOX),
                    "exportadas": len(demo),
                    "no_municipio": dentro,
                    "motivo": ("O municipio inteiro passa de 110 mil predios; "
                               "em GeoJSON o navegador nao aguenta. O mapa "
                               "carrega o recorte do nucleo urbano e desenha "
                               "o limite dele, para que a ausencia de predio "
                               "fora da caixa nao seja lida como ausencia de "
                               "edificacao."),
                    "completo": ("pipeline/run_all.py --completo gera "
                                 "edificacoes_municipio.geojson para o "
                                 "tippecanoe (PMTiles)")},
                "por_zona": {k: {"edificacoes": v["n"],
                                 "area_construida_m2": round(v["area_m2"], 1)}
                             for k, v in sorted(stats.items())}})

    print(f"  linhas lidas: {total:,}")
    print(f"  descartadas por confianca<{CONF_MIN} ou area<{AREA_MIN} m2: {descartadas:,}")
    print(f"  fora das zonas: {fora_zona:,}")
    print(f"  dentro das zonas: {dentro:,}")
    print("  top 8 zonas por numero de edificacoes:")
    for k, v in sorted(stats.items(), key=lambda kv: -kv[1]["n"])[:8]:
        print(f"    {k:<18} {v['n']:>7,} predios  "
              f"{v['area_m2']/1e6:>6.2f} km2 construidos")


if __name__ == "__main__":
    main(completo="--completo" in sys.argv)

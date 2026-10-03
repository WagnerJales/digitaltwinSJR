"""
Malha viaria de Sao Jose de Ribamar.

Entrada : SIG/RIBAMAR.shp  (extracao OSM, 5.592 linhas, WGS84)
Saida   : data/processados/vias.geojson

Normaliza a tag `highway` do OSM em 3 niveis de hierarquia para simbolizacao,
e descarta as classes que nao interessam ao gemeo digital (calcadas, trilhas,
faixas de pedestre) — que sao a maioria das feicoes e nao agregam leitura
urbanistica.
"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_geo import read_shapefile, write_geojson

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SHP = os.path.join(BASE, "SIG", "RIBAMAR")
PROC = os.path.join(BASE, "data", "processados")

HIERARQUIA = {
    "motorway": "estrutural", "motorway_link": "estrutural",
    "trunk": "estrutural", "trunk_link": "estrutural",
    "primary": "estrutural", "primary_link": "estrutural",
    "secondary": "arterial", "secondary_link": "arterial",
    "tertiary": "arterial", "tertiary_link": "arterial",
    "residential": "local", "unclassified": "local",
    "living_street": "local", "road": "local", "service": "local",
}
# classes descartadas: footway, path, cycleway, steps, track, pedestrian,
# construction, proposed, bridleway, corridor, crossing...


def main():
    print("VIAS")
    if not os.path.exists(SHP + ".shp"):
        sys.exit(f"ERRO: nao encontrei {SHP}.shp")

    feats = read_shapefile(SHP)
    print(f"  {len(feats)} feicoes lidas do shapefile")

    bruto = Counter(f["properties"].get("highway", "") for f in feats)
    print("  classes highway na origem:")
    for k, n in bruto.most_common(12):
        destino = HIERARQUIA.get(k, "descartada")
        print(f"    {k or '(vazio)':<18} {n:>5}  -> {destino}")

    out, descartadas = [], 0
    for f in feats:
        p = f["properties"]
        hier = HIERARQUIA.get(p.get("highway", ""))
        if hier is None:
            descartadas += 1
            continue
        nome = (p.get("name") or "").strip()
        props = {"nome": nome or None, "hierarquia": hier,
                 "tipo_osm": p.get("highway"),
                 "ref": (p.get("ref") or "").strip() or None,
                 "osm_id": p.get("osm_id")}
        # OSM as vezes traz listas serializadas; mantemos so o primeiro valor
        for k in ("nome", "ref"):
            if props[k] and ";" in props[k]:
                props[k] = props[k].split(";")[0].strip()
        out.append({"type": "Feature", "properties": props,
                    "geometry": f["geometry"]})

    ordem = {"estrutural": 0, "arterial": 1, "local": 2}
    out.sort(key=lambda f: ordem[f["properties"]["hierarquia"]])
    write_geojson(os.path.join(PROC, "vias.geojson"), out)

    dist = Counter(f["properties"]["hierarquia"] for f in out)
    print(f"  descartadas: {descartadas} (calcadas, trilhas, etc.)")
    for k in ("estrutural", "arterial", "local"):
        print(f"    {k:<12} {dist.get(k, 0):>5}")
    nomeadas = sum(1 for f in out if f["properties"]["nome"])
    print(f"  com nome: {nomeadas}/{len(out)} "
          f"({100*nomeadas/max(len(out),1):.0f}%)")


if __name__ == "__main__":
    main()

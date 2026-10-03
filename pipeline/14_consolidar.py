"""
Consolida as estatisticas das etapas 12 e 13 dentro do zoneamento.

Entrada : data/processados/zoneamento.geojson
          data/processados/stats_edificacoes.json
          data/processados/stats_enderecos.json
Saida   : reescreve zoneamento.geojson e parametros.json com os agregados

O que se ganha aqui: a Tabela 7 da LC 77/2025 diz o que a zona PERMITE (ATME,
ALML, altura). Cruzando os footprints do Open Buildings com o poligono da zona
obtemos o que ela TEM: a taxa de ocupacao observada. Os dois ficam claramente
separados no painel — 'parametros da lei' vs 'situacao observada' — porque a
distancia entre eles e justamente o que interessa a quem planeja.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_geo import write_geojson, write_json

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
PROC = os.path.join(BASE, "data", "processados")


def carrega(nome, obrigatorio=True):
    p = os.path.join(PROC, nome)
    if not os.path.exists(p):
        if obrigatorio:
            sys.exit(f"ERRO: falta {nome} — rode as etapas anteriores")
        print(f"  (sem {nome} — seguindo sem esses campos)")
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def main():
    print("CONSOLIDACAO")
    zon = carrega("zoneamento.geojson")
    edif = carrega("stats_edificacoes.json",
                   obrigatorio=False).get("por_zona", {})
    # o stats de enderecos passou a levar junto a tabela de especies; os
    # agregados por zona ficam em 'por_zona'
    ende = carrega("stats_enderecos.json", obrigatorio=False).get("por_zona", {})

    params = {}
    for feat in zon["features"]:
        p = feat["properties"]
        sigla = p["sigla"]
        area = p["area_m2"] or 0

        e = edif.get(sigla, {})
        a = ende.get(sigla, {})

        p["edificacoes"] = e.get("edificacoes", 0)
        p["area_construida_m2"] = e.get("area_construida_m2", 0.0)
        p["domicilios"] = a.get("domicilios", 0)
        p["enderecos"] = a.get("total", 0)
        p["estab_ensino"] = a.get("esp_4", 0)
        p["estab_saude"] = a.get("esp_5", 0)
        p["estab_outros"] = a.get("esp_6", 0)
        p["em_obra"] = a.get("esp_7", 0)

        # Indicadores derivados — OBSERVADOS, nao normativos.
        p["ocupacao_observada_pct"] = (
            round(100 * p["area_construida_m2"] / area, 1) if area else None)
        p["densidade_dom_ha"] = (
            round(p["domicilios"] / (area / 10_000), 2) if area else None)
        p["area_media_edif_m2"] = (
            round(p["area_construida_m2"] / p["edificacoes"], 1)
            if p["edificacoes"] else None)

        # Capacidade teorica de lotes pela area minima da zona. E um teto
        # bruto: ignora sistema viario, areas publicas e o relevo. Serve para
        # ordem de grandeza, nao para calculo de outorga.
        amin = p.get("area_min_m2")
        p["lotes_teoricos"] = int(area // amin) if amin and amin > 0 else None

        params[sigla] = {k: v for k, v in p.items() if k != "centroide"}

    write_geojson(os.path.join(PROC, "zoneamento.geojson"), zon["features"])
    write_json(os.path.join(PROC, "parametros.json"), params)

    tot_ed = sum(p["properties"]["edificacoes"] for p in zon["features"])
    tot_dom = sum(p["properties"]["domicilios"] for p in zon["features"])
    tot_area = sum(p["properties"]["area_construida_m2"] for p in zon["features"])
    print(f"  {tot_ed:,} edificacoes | {tot_dom:,} domicilios | "
          f"{tot_area/1e6:.2f} km2 construidos")
    print("  ocupacao observada (top 10):")
    ranked = sorted(zon["features"],
                    key=lambda f: -(f["properties"]["ocupacao_observada_pct"] or 0))
    for f in ranked[:10]:
        p = f["properties"]
        alt = p.get("altura_max_m")
        print(f"    {p['sigla']:<18} {p['ocupacao_observada_pct'] or 0:>5.1f}%  "
              f"altura max {(f'{alt:g} m' if alt else '   -'):>6}  "
              f"{p['densidade_dom_ha'] or 0:>6.2f} dom/ha")


if __name__ == "__main__":
    main()

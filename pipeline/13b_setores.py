"""
Setores censitarios do Censo 2022 (IBGE) para Sao Jose de Ribamar.

Entrada : SIG/censo2022/MA_setores_CD2022.shp   malha de setores do Maranhao
          SIG/censo2022/Agregados_por_setores_basico_BR.csv
Saida   : data/processados/setores.geojson
          data/processados/stats_setores.json

Por que isto importa aqui: ate agora a demografia entrava por PONTO (CNEFE) e
so era agregavel por zona inteira. O setor censitario e o menor recorte com
dado do Censo, e traz o que o CNEFE nao tem — POPULACAO, media de moradores e
situacao de ocupacao do domicilio. Com ele da para ler densidade dentro da
zona, e nao apenas a media da zona.

O CNEFE continua: ele localiza cada endereco, o setor nao. Sao respostas
diferentes — quantos moram aqui (setor) e onde exatamente estao (CNEFE).

Roda com a stdlib.
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_geo as G

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIG = os.path.join(BASE, "SIG", "censo2022")
PROC = os.path.join(BASE, "data", "processados")

MUNICIPIO = "2111201"          # Sao Jose de Ribamar - MA
SHP = os.path.join(SIG, "MA_setores_CD2022")
CSV = os.path.join(SIG, "Agregados_por_setores_basico_BR.csv")

# ---------------------------------------------------------------------------
# Variaveis do agregado "basico" do Censo 2022. Os codigos vXXXX nao dizem
# nada sozinhos; mapeamos para nomes e deixamos o significado a vista, porque
# trocar dois deles inverteria "vago" com "uso ocasional" sem ninguem notar.
# Conferidos contra o dicionario do IBGE e contra a identidade
# v0003 = v0007 + v0008 + v0009 (validada no fim deste script).
# ---------------------------------------------------------------------------
VARS = {
    "v0001": ("pessoas", "Total de pessoas residentes"),
    "v0002": ("domicilios", "Total de domicilios"),
    "v0003": ("dom_particulares", "Domicilios particulares"),
    "v0004": ("dom_coletivos", "Domicilios coletivos"),
    "v0005": ("moradores_por_dom", "Media de moradores em domicilios "
                                   "particulares ocupados"),
    "v0006": ("pct_imputados", "Percentual de domicilios imputados"),
    "v0007": ("dom_ocupados", "Domicilios particulares ocupados"),
    "v0008": ("dom_uso_ocasional", "Domicilios particulares nao ocupados de "
                                   "uso ocasional"),
    "v0009": ("dom_vagos", "Domicilios particulares nao ocupados vagos"),
}


def le_agregados():
    """
    Le o CSV nacional em streaming e guarda so as linhas do municipio.

    Sao 134 MB e ~450 mil setores no Brasil; carregar tudo em memoria seria
    desnecessario para as poucas centenas que interessam.
    """
    if not os.path.exists(CSV):
        print(f"  (sem {os.path.basename(CSV)} — seguindo so com a geometria)")
        return {}
    dados, lidas = {}, 0
    # o arquivo vem em latin-1, com ';' de separador e ',' de decimal
    with open(CSV, encoding="latin-1", newline="") as f:
        for linha in csv.DictReader(f, delimiter=";"):
            lidas += 1
            if linha.get("CD_MUN") != MUNICIPIO:
                continue
            reg = {"situacao": (linha.get("SITUACAO") or "").strip(),
                   "bairro": (linha.get("NM_BAIRRO") or "").strip(),
                   "distrito": (linha.get("NM_DIST") or "").strip(),
                   "area_km2_ibge": G.num_br(linha.get("AREA_KM2"))}
            for cod, (nome, _desc) in VARS.items():
                reg[nome] = G.num_br(linha.get(cod))
            dados[linha["CD_SETOR"].strip()] = reg
    print(f"  CSV: {lidas:,} setores no Brasil, {len(dados)} no municipio")
    return dados


def main():
    print("SETORES CENSITARIOS (Censo 2022 - IBGE)")
    if not os.path.exists(SHP + ".shp"):
        print(f"  ERRO: falta {SHP}.shp")
        print("  Baixe de geoftp.ibge.gov.br .../censo_2022/setores/shp/UF/"
              "MA_setores_CD2022.zip e descompacte em SIG/censo2022/")
        return

    feats_ma = G.read_shapefile(SHP)
    print(f"  malha do MA: {len(feats_ma):,} setores")

    agreg = le_agregados()

    # ---- so o municipio ----
    sjr = [f for f in feats_ma
           if str(f["properties"].get("CD_MUN", "")).strip() == MUNICIPIO]
    print(f"  setores em Sao Jose de Ribamar: {len(sjr)}")
    if not sjr:
        print("  ERRO: nenhum setor com CD_MUN = " + MUNICIPIO)
        return

    # ---- zona da lei em que cada setor cai ----
    zpath = os.path.join(PROC, "zoneamento.geojson")
    zonas = []
    if os.path.exists(zpath):
        import json
        with open(zpath, encoding="utf-8") as f:
            for z in json.load(f)["features"]:
                zonas.append((z["properties"]["sigla"], z["geometry"],
                              G.bbox(z["geometry"])))
    else:
        print("  (zoneamento.geojson ausente — setores sem zona)")

    def zona_de(geom):
        """Zona do centroide. Setor a cavaleiro de duas fica com a do centro."""
        c = G.centroid(geom)
        if not c:
            return None
        x, y = c
        for sigla, g, bb in zonas:
            if bb and not (bb[0] <= x <= bb[2] and bb[1] <= y <= bb[3]):
                continue
            if G.point_in_geom(x, y, g):
                return sigla
        return None

    saida, sem_dado, fora_zona = [], 0, 0
    for f in sjr:
        p = f["properties"]
        cd = str(p.get("CD_SETOR", "")).strip()
        a = agreg.get(cd, {})
        if not a:
            sem_dado += 1

        # A area vem da geometria, nao do campo do IBGE: e a mesma decisao ja
        # tomada nas zonas — o usuario clica no poligono, e e dele que a
        # densidade tem de sair.
        area_m2 = G.area_m2(f["geometry"])
        ha = area_m2 / 10_000.0
        pess = a.get("pessoas")
        dom = a.get("dom_particulares")
        ocup = a.get("dom_ocupados")

        z = zona_de(f["geometry"])
        if z is None:
            fora_zona += 1

        props = {
            "cd_setor": cd,
            "situacao": a.get("situacao") or "",
            "bairro": a.get("bairro") or "",
            "zona": z,
            "area_m2": round(area_m2, 1),
            "area_ha": round(ha, 3),
            "fonte": "IBGE, Censo 2022 — malha e agregados por setor",
        }
        for _cod, (nome, _d) in VARS.items():
            props[nome] = a.get(nome)
        # derivados: e por eles que o mapa e lido
        props["dens_hab_ha"] = round(pess / ha, 2) if pess and ha else None
        props["dens_dom_ha"] = round(dom / ha, 2) if dom and ha else None
        props["pct_vagos"] = (round(100 * a["dom_vagos"] / dom, 1)
                              if dom and a.get("dom_vagos") is not None else None)
        props["pct_uso_ocasional"] = (
            round(100 * a["dom_uso_ocasional"] / dom, 1)
            if dom and a.get("dom_uso_ocasional") is not None else None)
        props["pct_ocupados"] = (round(100 * ocup / dom, 1)
                                 if dom and ocup is not None else None)
        saida.append({"type": "Feature", "properties": props,
                      "geometry": f["geometry"]})

    G.write_geojson(os.path.join(PROC, "setores.geojson"), saida,
                    "setores censitarios 2022")

    # ---- conferencias e agregados ----
    pess = sum(f["properties"]["pessoas"] or 0 for f in saida)
    dom = sum(f["properties"]["dom_particulares"] or 0 for f in saida)
    ocup = sum(f["properties"]["dom_ocupados"] or 0 for f in saida)
    vag = sum(f["properties"]["dom_vagos"] or 0 for f in saida)
    oca = sum(f["properties"]["dom_uso_ocasional"] or 0 for f in saida)
    area = sum(f["properties"]["area_m2"] for f in saida)

    # identidade do Censo: particulares = ocupados + uso ocasional + vagos.
    # Se nao fechar, os codigos vXXXX foram mapeados errado.
    soma = ocup + oca + vag
    ok_ident = abs(soma - dom) <= max(1, dom * 0.001)

    por_zona = {}
    for f in saida:
        p = f["properties"]
        z = p["zona"] or "(fora do zoneamento)"
        d = por_zona.setdefault(z, {"setores": 0, "pessoas": 0,
                                    "domicilios": 0, "area_m2": 0.0})
        d["setores"] += 1
        d["pessoas"] += p["pessoas"] or 0
        d["domicilios"] += p["dom_particulares"] or 0
        d["area_m2"] += p["area_m2"]
    for z, d in por_zona.items():
        h = d["area_m2"] / 10_000.0
        d["dens_hab_ha"] = round(d["pessoas"] / h, 2) if h else None
        d["dens_dom_ha"] = round(d["domicilios"] / h, 2) if h else None
        d["area_km2"] = round(d["area_m2"] / 1e6, 3)

    G.write_json(os.path.join(PROC, "stats_setores.json"), {
        "fonte": "IBGE — Censo Demografico 2022, agregados por setor censitario",
        "municipio": MUNICIPIO,
        "setores": len(saida),
        "sem_agregado": sem_dado,
        "fora_do_zoneamento": fora_zona,
        "totais": {"pessoas": pess, "dom_particulares": dom,
                   "dom_ocupados": ocup, "dom_vagos": vag,
                   "dom_uso_ocasional": oca,
                   "area_km2": round(area / 1e6, 2)},
        "identidade_confere": ok_ident,
        "variaveis": {n: d for _c, (n, d) in VARS.items()},
        "por_zona": por_zona,
    })

    print(f"\n  {len(saida)} setores | {pess:,} pessoas | {dom:,} domicilios "
          f"particulares | {area/1e6:.1f} km2")
    print(f"  ocupados {ocup:,} | vagos {vag:,} "
          f"({100*vag/dom:.1f}%) | uso ocasional {oca:,} "
          f"({100*oca/dom:.1f}%)")
    print(f"  densidade media: {pess/(area/10_000):.2f} hab/ha")
    print("  identidade particulares = ocupados + ocasional + vagos: "
          + ("OK" if ok_ident else f"NAO FECHA ({soma:,} vs {dom:,})"))
    if sem_dado:
        print(f"  ATENCAO: {sem_dado} setor(es) sem linha no CSV de agregados")
    if fora_zona:
        print(f"  {fora_zona} setor(es) com centroide fora das zonas da lei")

    print("\n  densidade por zona (hab/ha):")
    for z, d in sorted(por_zona.items(),
                       key=lambda kv: -(kv[1]["dens_hab_ha"] or 0)):
        print(f"    {z:<22} {d['setores']:>4} setores  "
              f"{d['pessoas']:>7,} hab  {d['area_km2']:>7.2f} km2  "
              f"{d['dens_hab_ha'] or 0:>7.2f} hab/ha")


if __name__ == "__main__":
    main()

"""
Zoneamento REAL de Sao Jose de Ribamar - MA.

Entrada : SIG/ZONEAMENTO_RIBAMAR.kmz   (44 zonas, exportado do ArcGIS/Google Earth)
Saida   : data/processados/zoneamento.geojson
          data/processados/parametros.json

Os parametros urbanisticos vem embutidos no proprio KMZ, na tabela HTML da
descricao de cada placemark:

    TESTAD_MIN  testada minima do lote (m)
    AREA_MIN    area minima do lote (m2)
    AFASTAM_FR  afastamento frontal (m)
    GABAR_MAX   gabarito maximo (NUMERO DE PAVIMENTOS, nao metros)

Zonas ambientais usam esses mesmos campos para gravar uma taxa de ocupacao
maxima em percentual ("10%", "5%", "0,5%") ou "n/a" quando nao se aplica —
tratamos os tres casos separadamente para nao inventar valor nenhum.

ATENCAO: nao ha coeficiente de aproveitamento (CA) nem taxa de permeabilidade
nesta base. O app nao deve exibir esses campos como se existissem.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_geo import (read_kmz_placemarks, area_m2, centroid, num_br,
                     write_geojson, write_json)

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
KMZ = os.path.join(BASE, "SIG", "ZONEAMENTO_RIBAMAR.kmz")
PROC = os.path.join(BASE, "data", "processados")

# Pe-direito adotado para converter pavimentos em metros na visualizacao 3D.
# E uma CONVENCAO DE DESENHO, nao um parametro da lei.
PE_DIREITO_M = 3.0

# ----------------------------------------------------------------------
# Familias de zona -> cor. O app le a cor daqui (nada de sigla hardcoded
# no HTML: se o zoneamento mudar, a legenda acompanha).
# ----------------------------------------------------------------------
FAMILIAS = [
    (r"^ZC$",           "central",     "Zona Central",              "#b02e0c"),
    (r"^ZR\s*\d+$",     "residencial", "Zonas Residenciais",        "#f4a259"),
    (r"^ZDS",           "social",      "Desenvolvimento Social",    "#9b5de5"),
    (r"^ZEU$",          "expansao",    "Expansao Urbana",           "#f7cf6b"),
    (r"^Z(I|IN|IPA)\s", "industrial",  "Industriais",               "#5b7db1"),
    (r"^ZIS|^ZISTR$",   "sanitario",   "Interesse Sanitario",       "#00a6a6"),
    (r"^ZITC",          "turistico",   "Interesse Turistico/Cultural", "#e05780"),
    (r"^(ZPA|ZPAI|ZPAT|ZPI|ZT|APA)", "ambiental", "Protecao Ambiental", "#3fa66a"),
    (r"^ZR[A-Z]+$",     "rural",       "Zonas Rurais",              "#a3b18a"),
]


def classificar(sigla):
    s = re.sub(r"\s*-\s*", " ", sigla).strip().upper()
    s = re.sub(r"\s+", " ", s)
    for padrao, chave, rotulo, cor in FAMILIAS:
        if re.search(padrao, s):
            return chave, rotulo, cor
    return "outra", "Outras", "#999999"


def pct(bruto):
    """'10%' -> 10.0 ; qualquer outra coisa -> None."""
    if bruto and str(bruto).strip().endswith("%"):
        return num_br(str(bruto).strip()[:-1])
    return None


def main():
    print("ZONEAMENTO")
    if not os.path.exists(KMZ):
        sys.exit(f"ERRO: nao encontrei {KMZ}")

    placemarks = read_kmz_placemarks(KMZ)
    print(f"  {len(placemarks)} zonas lidas do KMZ")

    feats, params = [], {}
    for pm in placemarks:
        p = pm["properties"]
        sigla = (p.get("Sigla") or p.get("_name") or "").strip()
        sigla = re.sub(r"\s*-\s*", " ", sigla)          # 'ZIS - CA 1' -> 'ZIS CA 1'
        sigla = re.sub(r"\s+", " ", sigla).strip()
        zoneamento = (p.get("Zoneamento") or p.get("_name") or sigla).strip()
        # 'ZR 5 - ZONA RESIDENCIAL 5' -> 'Zona Residencial 5'
        nome = re.sub(r"^\s*" + re.escape(sigla) + r"\s*-\s*", "", zoneamento) \
            if " - " in zoneamento else zoneamento
        nome = nome.strip().title() or zoneamento

        familia, familia_rotulo, cor = classificar(sigla)

        gabarito = num_br(p.get("GABAR_MAX"))
        area_min = num_br(p.get("AREA_MIN"))
        testada = num_br(p.get("TESTAD_MIN"))
        afast = num_br(p.get("AFASTAM_FR"))
        ocup_pct = pct(p.get("AREA_MIN")) or pct(p.get("TESTAD_MIN"))

        # Area / Shape_STAr sao atributos da base; area_calc e a area do
        # poligono realmente exportado no KMZ. Divergem em varias zonas
        # (ver AVISOs e o relatorio no README): os campos nao foram
        # recalculados apos a ultima edicao das geometrias. Exibimos a area
        # da geometria — e ela que o usuario ve e clica no mapa — e
        # preservamos a declarada para auditoria.
        area_base = num_br(p.get("Shape_STAr")) or num_br(p.get("Area"))
        area_calc = area_m2(pm["geometry"])
        divergencia = (abs(area_calc - area_base) / area_base * 100
                       if area_base else None)

        props = {
            "sigla": sigla,
            "nome": nome,
            "zoneamento": zoneamento,
            "familia": familia,
            "familia_rotulo": familia_rotulo,
            "cor": cor,
            "area_m2": round(area_calc, 1),
            "area_base_m2": round(area_base, 1) if area_base else None,
            "divergencia_area_pct": round(divergencia, 1) if divergencia else None,
            "revisar_area": bool(divergencia and divergencia > 2),
            "gabarito_max_pav": int(gabarito) if gabarito else None,
            "gabarito_max_m": round(gabarito * PE_DIREITO_M, 1) if gabarito else None,
            "area_min_m2": area_min,
            "testada_min_m": testada,
            "afastamento_frontal_m": afast,
            "ocupacao_max_pct": ocup_pct,
            # valores originais preservados: 'n/a' e '10%' sao informacao,
            # nao ausencia de dado
            "gabarito_bruto": p.get("GABAR_MAX"),
            "area_min_bruto": p.get("AREA_MIN"),
            "testada_min_bruto": p.get("TESTAD_MIN"),
            "afastamento_bruto": p.get("AFASTAM_FR"),
        }
        props["centroide"] = centroid(pm["geometry"])
        feats.append({"type": "Feature", "properties": props,
                      "geometry": pm["geometry"]})
        params[sigla] = {k: v for k, v in props.items() if k != "centroide"}

        if divergencia and divergencia > 2:
            print(f"  REVISAR {sigla}: geometria {area_calc/1e6:.2f} km2 vs "
                  f"Shape_STAr {area_base/1e6:.2f} km2 ({divergencia:+.1f}%)")

    feats.sort(key=lambda f: (f["properties"]["familia"], f["properties"]["sigla"]))
    write_geojson(os.path.join(PROC, "zoneamento.geojson"), feats)
    write_json(os.path.join(PROC, "parametros.json"), params)

    total = sum(f["properties"]["area_m2"] for f in feats)
    print(f"  area total zoneada: {total/1e6:.1f} km2")
    fam = {}
    for f in feats:
        fam.setdefault(f["properties"]["familia_rotulo"], []).append(
            f["properties"]["sigla"])
    for k, v in sorted(fam.items()):
        print(f"    {k:<30} {len(v):>2} zonas  {', '.join(sorted(v))[:70]}")
    faltando = [f["properties"]["sigla"] for f in feats
                if f["properties"]["gabarito_max_pav"] is None]
    if faltando:
        print(f"  sem gabarito definido ({len(faltando)}): {', '.join(faltando)}")


if __name__ == "__main__":
    main()

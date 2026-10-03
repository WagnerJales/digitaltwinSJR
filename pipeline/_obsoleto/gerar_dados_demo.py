"""
Gera dados DEMO (fictícios) para testar o Gêmeo Digital de São José de Ribamar - MA.

ATENÇÃO: geometrias e parâmetros são FICTÍCIOS, apenas para validar o app.
Substitua pelos dados reais rodando 01_baixar_bases.py, 02_processar_zoneamento.py
e 03_processar_lotes.py.

Saída: ../data/processados/{zoneamento,lotes,edificacoes,vias}.geojson
"""
import json
import math
import random
import os

random.seed(42)

# Centro aproximado da sede de São José de Ribamar - MA
LON0, LAT0 = -44.0540, -2.5615

# fatores de conversão aproximados (graus por metro) nessa latitude
M_LON = 1.0 / 111320.0
M_LAT = 1.0 / 110570.0

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "processados")
os.makedirs(OUT, exist_ok=True)


def offset(x_m, y_m):
    """Desloca (m) a partir do centro e retorna [lon, lat]."""
    return [round(LON0 + x_m * M_LON, 6), round(LAT0 + y_m * M_LAT, 6)]


def rect(x, y, w, h):
    return [[offset(x, y), offset(x + w, y), offset(x + w, y + h),
             offset(x, y + h), offset(x, y)]]


# ----------------------------------------------------------------------
# 1. ZONEAMENTO DEMO — 6 zonas em faixas (siglas genéricas; troque pelas
#    siglas reais da Lei de Zoneamento 2025 de SJR)
# ----------------------------------------------------------------------
zonas_def = [
    ("ZC",   "Zona Central (DEMO)",              -1200, -400,  2400, 800),
    ("ZR1",  "Zona Residencial 1 (DEMO)",        -1200,  400,  2400, 800),
    ("ZR2",  "Zona Residencial 2 (DEMO)",        -1200, -1200, 2400, 800),
    ("ZEIS", "Zona Especial Int. Social (DEMO)", -2000, -1200,  800, 2400),
    ("ZI",   "Zona de Interesse Indust. (DEMO)",  1200, -1200,  800, 1600),
    ("ZPA",  "Zona de Proteção Ambiental (DEMO)", 1200,  400,   800, 800),
]
zoneamento = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"sigla": s, "nome": n},
            "geometry": {"type": "Polygon", "coordinates": rect(x, y, w, h)},
        }
        for s, n, x, y, w, h in zonas_def
    ],
}

# ----------------------------------------------------------------------
# 2. LOTES DEMO — quadras 100x80 m com lotes de ~12x30 m
# ----------------------------------------------------------------------
lotes_feats = []
edifs_feats = []
lote_id = 0
for qx in range(-10, 10):
    for qy in range(-10, 10):
        bx, by = qx * 120.0, qy * 100.0  # origem da quadra (ruas de 20 m)
        # zona do centróide da quadra
    	# (busca simples nas faixas definidas acima)
        cx, cy = bx + 50, by + 40
        zona = None
        for s, n, x, y, w, h in zonas_def:
            if x <= cx <= x + w and y <= cy <= y + h:
                zona = s
                break
        if zona is None:
            continue
        for row in range(2):          # 2 fileiras de lotes por quadra
            for col in range(8):      # 8 lotes por fileira
                lote_id += 1
                lx = bx + col * 12.5
                ly = by + row * 40.0
                w_l, h_l = 12.5, 40.0
                area = round(w_l * h_l, 1)
                lotes_feats.append({
                    "type": "Feature",
                    "properties": {
                        "id_lote": f"SJR-DEMO-{lote_id:05d}",
                        "area_m2": area,
                        "zona": zona,
                        "logradouro": f"Rua Demo {abs(qx)+1:02d}",
                        "testada_m": w_l,
                    },
                    "geometry": {"type": "Polygon",
                                 "coordinates": rect(lx, ly, w_l, h_l)},
                })
                # edificação: recuo de 2 m, altura conforme a zona
                if random.random() < 0.85 and zona != "ZPA":
                    alturas = {"ZC": (6, 36), "ZR1": (3, 9), "ZR2": (3, 12),
                               "ZEIS": (3, 6), "ZI": (5, 12)}
                    hmin, hmax = alturas.get(zona, (3, 9))
                    h_ed = round(random.uniform(hmin, hmax), 1)
                    edifs_feats.append({
                        "type": "Feature",
                        "properties": {"altura_m": h_ed,
                                       "id_lote": f"SJR-DEMO-{lote_id:05d}"},
                        "geometry": {"type": "Polygon",
                                     "coordinates": rect(lx + 2, ly + 2,
                                                         w_l - 4, h_l - 15)},
                    })

lotes = {"type": "FeatureCollection", "features": lotes_feats}
edificacoes = {"type": "FeatureCollection", "features": edifs_feats}

# ----------------------------------------------------------------------
# 3. VIAS DEMO — malha simples
# ----------------------------------------------------------------------
vias_feats = []
for qx in range(-10, 11):
    x = qx * 120.0 - 10
    vias_feats.append({
        "type": "Feature",
        "properties": {"nome": f"Rua Demo V{qx+11:02d}", "hierarquia": "local"},
        "geometry": {"type": "LineString",
                     "coordinates": [offset(x, -1250), offset(x, 1250)]},
    })
for qy in range(-10, 11):
    y = qy * 100.0 - 10
    hier = "arterial" if qy % 5 == 0 else "local"
    vias_feats.append({
        "type": "Feature",
        "properties": {"nome": f"Av. Demo H{qy+11:02d}", "hierarquia": hier},
        "geometry": {"type": "LineString",
                     "coordinates": [offset(-2050, y), offset(2050, y)]},
    })
vias = {"type": "FeatureCollection", "features": vias_feats}

for nome, fc in [("zoneamento", zoneamento), ("lotes", lotes),
                 ("edificacoes", edificacoes), ("vias", vias)]:
    path = os.path.join(OUT, f"{nome}.geojson")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False)
    print(f"{nome}: {len(fc['features'])} feições -> {path}")

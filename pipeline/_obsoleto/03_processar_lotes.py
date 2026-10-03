"""
Processa o cadastro de lotes (quando a Prefeitura fornecer).

Entrada:
    ../data/brutos/lotes_sjr.(shp|gpkg)      <- cadastro imobiliário georreferenciado
    ../data/processados/zoneamento.geojson   <- gerado pelo script 02

Faz o spatial join lote->zona (zona do centróide do lote, replicando o
comportamento da OSPA: lote em mais de uma zona reporta percentuais).

Saída:
    ../data/processados/lotes.geojson
"""
import os
import geopandas as gpd

BASE = os.path.join(os.path.dirname(__file__), "..")
COLUNA_ID = "inscricao"          # <-- AJUSTAR: campo de inscrição cadastral
ARQ_LOTES = os.path.join(BASE, "data", "brutos", "lotes_sjr.shp")

lotes = gpd.read_file(ARQ_LOTES).to_crs(4326)
zonas = gpd.read_file(os.path.join(BASE, "data", "processados",
                                   "zoneamento.geojson"))

# área em m² calculada em projeção métrica (UTM 23S - SIRGAS 2000)
lotes["area_m2"] = lotes.to_crs(31983).area.round(1)
lotes["id_lote"] = lotes[COLUNA_ID].astype(str)

# zona pelo ponto interno do lote (evita ambiguidade de fronteira)
pts = lotes.copy()
pts["geometry"] = lotes.representative_point()
join = gpd.sjoin(pts, zonas[["sigla", "geometry"]], how="left",
                 predicate="within")
lotes["zona"] = join["sigla"].values

sem_zona = lotes["zona"].isna().sum()
if sem_zona:
    print(f"AVISO: {sem_zona} lotes fora de qualquer zona")

lotes = lotes[["id_lote", "area_m2", "zona", "geometry"]]
out = os.path.join(BASE, "data", "processados", "lotes.geojson")
lotes.to_file(out, driver="GeoJSON")
print(f"ok -> {out} ({len(lotes)} lotes)")

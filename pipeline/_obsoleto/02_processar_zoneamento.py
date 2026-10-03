"""
Processa o zoneamento REAL de SJR.

Entrada:
    ../data/brutos/zoneamento_sjr.(shp|gpkg|geojson)  <- SEU shapefile vetorizado
    ../data/parametros_urbanisticos.csv               <- tabela por zona (da Lei 2025)

O join é feito pela coluna de sigla da zona. Ajuste COLUNA_SIGLA abaixo
para o nome do campo no seu shapefile.

Saída:
    ../data/processados/zoneamento.geojson  (WGS84, com parâmetros embutidos)
"""
import os
import geopandas as gpd
import pandas as pd

BASE = os.path.join(os.path.dirname(__file__), "..")
COLUNA_SIGLA = "sigla"          # <-- AJUSTAR para o campo do seu arquivo
ARQ_ZONEAMENTO = os.path.join(BASE, "data", "brutos", "zoneamento_sjr.shp")

gdf = gpd.read_file(ARQ_ZONEAMENTO)
print(f"{len(gdf)} zonas lidas | CRS original: {gdf.crs}")
print("Colunas:", list(gdf.columns))

# reprojetar para WGS84 (obrigatório para tiles/web)
gdf = gdf.to_crs(4326)

# normalizar sigla e fazer o join com os parâmetros
gdf["sigla"] = gdf[COLUNA_SIGLA].astype(str).str.strip().str.upper()
params = pd.read_csv(os.path.join(BASE, "data",
                                  "parametros_urbanisticos.csv"))
params["sigla"] = params["sigla"].str.strip().str.upper()

sem_param = set(gdf["sigla"]) - set(params["sigla"])
if sem_param:
    print(f"AVISO: zonas sem parâmetros no CSV: {sorted(sem_param)}")

gdf = gdf.merge(params, on="sigla", how="left", suffixes=("", "_p"))
if "nome" not in gdf.columns and "nome_p" in gdf.columns:
    gdf["nome"] = gdf["nome_p"]

cols = ["sigla", "nome", "ca_basico", "ca_maximo", "taxa_ocupacao_pct",
        "taxa_permeabilidade_pct", "gabarito_max_m", "recuo_frontal_m",
        "recuo_lateral_m", "usos_permitidos", "geometry"]
gdf = gdf[[c for c in cols if c in gdf.columns]]

out = os.path.join(BASE, "data", "processados", "zoneamento.geojson")
gdf.to_file(out, driver="GeoJSON")
print(f"ok -> {out}")

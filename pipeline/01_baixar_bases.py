"""
Baixa bases públicas de São José de Ribamar - MA (código IBGE 2111201).
Rodar na SUA máquina (precisa de internet livre).

Dependências:
    pip install geopandas osmnx requests

Saídas em ../data/brutos/:
    limite_municipal.geojson    (IBGE, malha municipal)
    setores_censitarios.gpkg    (IBGE, Censo 2022 — via geobr, opcional)
    edificacoes_osm.geojson     (OpenStreetMap)
    vias_osm.geojson            (OpenStreetMap)
"""
import os
import requests

COD_IBGE = "2111201"  # São José de Ribamar - MA
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "brutos")
os.makedirs(OUT, exist_ok=True)

# ----------------------------------------------------------------------
# 1. Limite municipal — API de malhas do IBGE
# ----------------------------------------------------------------------
url = (f"https://servicodados.ibge.gov.br/api/v3/malhas/municipios/{COD_IBGE}"
       "?formato=application/vnd.geo+json&qualidade=maxima")
r = requests.get(url, timeout=60)
r.raise_for_status()
with open(os.path.join(OUT, "limite_municipal.geojson"), "w",
          encoding="utf-8") as f:
    f.write(r.text)
print("limite_municipal.geojson ok")

# ----------------------------------------------------------------------
# 2. Edificações e vias — OpenStreetMap via osmnx
#    (cobertura de edificações em SJR é parcial; para 3D completo,
#     avaliar Google Open Buildings ou Microsoft Building Footprints)
# ----------------------------------------------------------------------
import osmnx as ox

place = "São José de Ribamar, Maranhão, Brazil"

edifs = ox.features_from_place(place, tags={"building": True})
edifs = edifs[edifs.geometry.type.isin(["Polygon", "MultiPolygon"])]
# altura: usa building:levels quando existir (3 m por pavimento), senão 4,5 m
def altura(row):
    try:
        return float(row.get("height"))
    except (TypeError, ValueError):
        pass
    try:
        return float(row.get("building:levels")) * 3.0
    except (TypeError, ValueError):
        return 4.5
edifs["altura_m"] = edifs.apply(altura, axis=1)
edifs[["altura_m", "geometry"]].to_file(
    os.path.join(OUT, "edificacoes_osm.geojson"), driver="GeoJSON")
print(f"edificacoes_osm.geojson ok ({len(edifs)} feições)")

grafo = ox.graph_from_place(place, network_type="drive")
vias = ox.graph_to_gdfs(grafo, nodes=False)
vias = vias.reset_index()[["name", "highway", "geometry"]]
vias.columns = ["nome", "hierarquia", "geometry"]


def achatar(v):
    """
    Tags do OSM viram list quando o way tem varios valores (ex.: highway
    ['residential','service']). O driver GeoJSON rejeita campo de tipo lista,
    entao ficamos com o primeiro valor.
    """
    if isinstance(v, (list, tuple)):
        return v[0] if v else None
    return v


for col in ("nome", "hierarquia"):
    vias[col] = vias[col].map(achatar)
vias.to_file(os.path.join(OUT, "vias_osm.geojson"), driver="GeoJSON")
print(f"vias_osm.geojson ok ({len(vias)} feições)")

# ----------------------------------------------------------------------
# 3. Setores censitários 2022 (opcional — análises demográficas)
# ----------------------------------------------------------------------
try:
    import geobr
    setores = geobr.read_census_tract(code_tract=2111201, year=2022)
    setores.to_file(os.path.join(OUT, "setores_censitarios.gpkg"),
                    driver="GPKG")
    print(f"setores_censitarios.gpkg ok ({len(setores)} setores)")
except Exception as e:  # geobr é opcional
    print(f"setores censitários: pulado ({e})")

"""
Utilitarios geoespaciais em Python puro (somente stdlib).

Motivacao: o ambiente roda Python 3.14, para o qual ainda nao ha wheels de
geopandas/fiona/shapely. Como todos os dados de entrada ja estao em WGS84
(EPSG:4326) e o municipio cabe numa caixa de ~25 km, nao precisamos de uma
engine de reprojecao: uma projecao equirretangular local em torno do
centroide erra menos de 0,1% em area nessa escala.

Cobre o que o pipeline precisa: ler shapefile (SHP+DBF), ler KML/KMZ,
ler WKT de poligono, calcular area em m2, testar ponto-em-poligono,
converter UTM->WGS84 e escrever GeoJSON.
"""
import json
import math
import os
import re
import struct
import sys

# ---------------------------------------------------------------------------
# Console em UTF-8.
#
# Efeito colateral de import, e proposital: todos os scripts do pipeline
# importam este modulo, e sem isto o console padrao do Windows (cp1252)
# derruba a execucao ao imprimir "≥", "²" ou qualquer acento — nao um aviso,
# um UnicodeEncodeError que aborta a etapa. Dependia de a pessoa lembrar de
# exportar PYTHONIOENCODING antes de rodar; agora nao depende.
# ---------------------------------------------------------------------------
for _fluxo in (sys.stdout, sys.stderr):
    try:
        _fluxo.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass          # ambiente sem reconfigure ou fluxo redirecionado

import zipfile
from html import unescape

# ---------------------------------------------------------------------------
# UTM -> WGS84
#
# Os memoriais descritivos da Lei Complementar 77/2025 vem em UTM zona 23S,
# datum SIRGAS 2000. Aqui a projecao equirretangular do resto do modulo nao
# serve: precisamos da inversa exata da Transversa de Mercator, senao o
# poligono sai deslocado de centenas de metros.
#
# SIRGAS 2000 usa o elipsoide GRS80; a diferenca para o WGS84 esta na 11a casa
# do achatamento (<0,1 mm no terreno), entao a conversao e direta.
# Formulacao: Snyder, "Map Projections - A Working Manual" (USGS PP 1395), 8-.
# ---------------------------------------------------------------------------
GRS80_A = 6378137.0
GRS80_F = 1.0 / 298.257222101
UTM_K0 = 0.9996


def utm_para_wgs84(easting, northing, zona=23, sul=True):
    """Converte UTM (m) em (lon, lat) graus decimais."""
    a, f = GRS80_A, GRS80_F
    e2 = 2 * f - f * f
    ep2 = e2 / (1 - e2)

    x = easting - 500000.0
    y = northing - (10000000.0 if sul else 0.0)
    lon0 = math.radians(zona * 6 - 183)

    m = y / UTM_K0
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    mu = m / (a * (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256))
    p1 = (mu
          + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
          + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
          + (151 * e1**3 / 96) * math.sin(6 * mu)
          + (1097 * e1**4 / 512) * math.sin(8 * mu))

    sin1, cos1, tan1 = math.sin(p1), math.cos(p1), math.tan(p1)
    c1 = ep2 * cos1 * cos1
    t1 = tan1 * tan1
    n1 = a / math.sqrt(1 - e2 * sin1 * sin1)
    r1 = a * (1 - e2) / (1 - e2 * sin1 * sin1) ** 1.5
    d = x / (n1 * UTM_K0)

    lat = p1 - (n1 * tan1 / r1) * (
        d**2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1 * c1 - 9 * ep2) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1 * t1 - 252 * ep2 - 3 * c1 * c1)
        * d**6 / 720)
    lon = lon0 + (
        d
        - (1 + 2 * t1 + c1) * d**3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1 * c1 + 8 * ep2 + 24 * t1 * t1)
        * d**5 / 120) / cos1

    return math.degrees(lon), math.degrees(lat)


def area_utm_m2(pontos):
    """Area por shoelace direto em UTM (plano) — referencia independente."""
    n = len(pontos)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x1, y1 = pontos[i]
        x2, y2 = pontos[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0

# ----------------------------------------------------------------------
# Shapefile (SHP + DBF)
# ----------------------------------------------------------------------
SHP_NULL, SHP_POINT, SHP_POLYLINE, SHP_POLYGON = 0, 1, 3, 5


def _dbf_read(path, encoding="utf-8"):
    """Le um .dbf inteiro e devolve lista de dicts (na ordem dos registros)."""
    with open(path, "rb") as f:
        head = f.read(32)
        nrec, hlen, rlen = struct.unpack("<IHH", head[4:12])
        fields = []
        while True:
            fd = f.read(32)
            if not fd or fd[0] == 0x0D:
                break
            name = fd[:11].split(b"\x00")[0].decode("latin-1").strip()
            fields.append((name, chr(fd[11]), fd[16]))
        f.seek(hlen)
        rows = []
        for _ in range(nrec):
            rec = f.read(rlen)
            if len(rec) < rlen:
                break
            if rec[0:1] == b"*":          # registro marcado como deletado
                rows.append(None)
                continue
            off, out = 1, {}
            for name, ftype, flen in fields:
                raw = rec[off:off + flen]
                off += flen
                try:
                    val = raw.decode(encoding).strip()
                except UnicodeDecodeError:
                    val = raw.decode("latin-1").strip()
                if ftype == "N" and val:
                    try:
                        val = float(val) if ("." in val or "," in val) else int(val)
                    except ValueError:
                        pass
                out[name] = val
            rows.append(out)
        return rows


def _shp_read(path):
    """Le um .shp e devolve lista de geometrias GeoJSON (ou None)."""
    with open(path, "rb") as f:
        data = f.read()
    geoms, pos, end = [], 100, len(data)
    while pos < end:
        _num, clen = struct.unpack(">II", data[pos:pos + 8])
        pos += 8
        body = data[pos:pos + clen * 2]
        pos += clen * 2
        if len(body) < 4:
            geoms.append(None)
            continue
        stype, = struct.unpack("<I", body[:4])
        if stype == SHP_NULL:
            geoms.append(None)
        elif stype == SHP_POINT:
            x, y = struct.unpack("<2d", body[4:20])
            geoms.append({"type": "Point", "coordinates": [_r(x), _r(y)]})
        elif stype in (SHP_POLYLINE, SHP_POLYGON):
            nparts, npoints = struct.unpack("<2I", body[36:44])
            o = 44
            parts = struct.unpack(f"<{nparts}I", body[o:o + 4 * nparts])
            o += 4 * nparts
            flat = struct.unpack(f"<{npoints * 2}d", body[o:o + 16 * npoints])
            rings = []
            for i, start in enumerate(parts):
                stop = parts[i + 1] if i + 1 < nparts else npoints
                rings.append([[_r(flat[j * 2]), _r(flat[j * 2 + 1])]
                              for j in range(start, stop)])
            if stype == SHP_POLYLINE:
                geoms.append({"type": "LineString", "coordinates": rings[0]}
                             if len(rings) == 1 else
                             {"type": "MultiLineString", "coordinates": rings})
            else:
                geoms.append(_rings_to_polygon(rings))
        else:
            geoms.append(None)                 # tipos Z/M nao usados aqui
    return geoms


def _r(v, nd=6):
    """Arredonda coordenada. 6 casas ~ 11 cm; corta o arquivo pela metade."""
    return round(v, nd)


def _rings_to_polygon(rings):
    """
    No shapefile, aneis horarios sao exteriores e anti-horarios sao buracos.
    Agrupa em Polygon/MultiPolygon conforme a convencao GeoJSON.
    """
    polys, cur = [], None
    for ring in rings:
        if signed_area(ring) < 0:              # horario -> novo exterior
            if cur:
                polys.append(cur)
            cur = [ring]
        else:
            if cur is None:                    # buraco orfao: trata como ilha
                cur = [ring]
            else:
                cur.append(ring)
    if cur:
        polys.append(cur)
    polys = [_orient(p) for p in polys]
    if len(polys) == 1:
        return {"type": "Polygon", "coordinates": polys[0]}
    return {"type": "MultiPolygon", "coordinates": polys}


def read_shapefile(base_path, encoding="utf-8"):
    """
    Le <base>.shp + <base>.dbf. Devolve lista de features GeoJSON.
    Usa o .cpg como encoding quando existir.
    """
    cpg = base_path + ".cpg"
    if os.path.exists(cpg):
        with open(cpg) as f:
            enc = f.read().strip()
            if enc:
                encoding = enc
    geoms = _shp_read(base_path + ".shp")
    props = _dbf_read(base_path + ".dbf", encoding)
    feats = []
    for g, p in zip(geoms, props):
        if g is None or p is None:
            continue
        feats.append({"type": "Feature", "properties": p, "geometry": g})
    return feats


# ----------------------------------------------------------------------
# KML / KMZ
# ----------------------------------------------------------------------
def read_kmz_placemarks(path):
    """
    Le um KMZ/KML exportado do ArcGIS/Google Earth.

    Os atributos vem numa tabela HTML dentro do <description><![CDATA[...]]>;
    a primeira celula e o titulo e as demais sao pares rotulo/valor.
    Devolve features GeoJSON com esses atributos como properties.
    """
    if path.lower().endswith(".kmz"):
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.lower().endswith(".kml"))
            kml = z.read(name).decode("utf-8", "replace")
    else:
        with open(path, encoding="utf-8") as f:
            kml = f.read()

    feats = []
    for pm in re.findall(r"<Placemark\b.*?</Placemark>", kml, re.S):
        props = {}
        m = re.search(r"<description><!\[CDATA\[(.*?)\]\]></description>", pm, re.S)
        if m:
            cells = [unescape(re.sub(r"<.*?>", " ", c)).strip()
                     for c in re.findall(r"<td>(.*?)</td>", m.group(1), re.S)]
            cells = cells[1:]                  # descarta a celula de titulo
            props = {cells[i]: cells[i + 1] for i in range(0, len(cells) - 1, 2)}
        nm = re.search(r"<name>(.*?)</name>", pm, re.S)
        if nm:
            props.setdefault("_name", unescape(nm.group(1)).strip())

        polys = []
        for poly in re.findall(r"<Polygon>.*?</Polygon>", pm, re.S):
            rings = []
            out = re.search(r"<outerBoundaryIs>.*?<coordinates>(.*?)</coordinates>",
                            poly, re.S)
            if not out:
                continue
            rings.append(_kml_coords(out.group(1)))
            for inn in re.findall(
                    r"<innerBoundaryIs>.*?<coordinates>(.*?)</coordinates>",
                    poly, re.S):
                rings.append(_kml_coords(inn))
            polys.append(_orient(rings))
        if not polys:
            continue
        geom = ({"type": "Polygon", "coordinates": polys[0]} if len(polys) == 1
                else {"type": "MultiPolygon", "coordinates": polys})
        feats.append({"type": "Feature", "properties": props, "geometry": geom})
    return feats


def _kml_coords(text):
    """'lon,lat,alt lon,lat,alt ...' -> [[lon,lat], ...] (descarta altitude)."""
    ring = []
    for tok in text.split():
        parts = tok.split(",")
        if len(parts) >= 2:
            ring.append([_r(float(parts[0])), _r(float(parts[1]))])
    if ring and ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring


# ----------------------------------------------------------------------
# WKT (apenas POLYGON, que e o que o Google Open Buildings usa)
# ----------------------------------------------------------------------
def wkt_polygon(wkt):
    m = re.match(r"\s*POLYGON\s*\(\((.*)\)\)\s*$", wkt, re.S | re.I)
    if not m:
        return None
    ring = []
    for pair in m.group(1).split(","):
        xy = pair.split()
        if len(xy) >= 2:
            ring.append([_r(float(xy[0])), _r(float(xy[1]))])
    if len(ring) < 4:
        return None
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return {"type": "Polygon", "coordinates": _orient([ring])}


# ----------------------------------------------------------------------
# Geometria
# ----------------------------------------------------------------------
def signed_area(ring):
    """Area com sinal em graus^2. Positiva = anti-horario (CCW)."""
    s = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i]
        x2, y2 = ring[i + 1]
        s += x1 * y2 - x2 * y1
    return s / 2.0


def _orient(rings):
    """GeoJSON RFC 7946: exterior anti-horario, buracos horarios."""
    out = []
    for i, ring in enumerate(rings):
        ccw = signed_area(ring) > 0
        want_ccw = (i == 0)
        out.append(ring if ccw == want_ccw else ring[::-1])
    return out


def area_m2(geom):
    """
    Area em m2 por projecao equirretangular local (centrada no proprio
    poligono). Erro < 0,1% na extensao de um municipio.
    """
    polys = _as_polygons(geom)
    if not polys:
        return 0.0
    lats = [pt[1] for poly in polys for ring in poly for pt in ring]
    lat0 = math.radians(sum(lats) / len(lats))
    kx = 111320.0 * math.cos(lat0)
    ky = 110574.0
    total = 0.0
    for poly in polys:
        for i, ring in enumerate(poly):
            m = [[x * kx, y * ky] for x, y in ring]
            a = abs(signed_area(m))
            total += a if i == 0 else -a       # subtrai buracos
    return total


def bbox(geom):
    xs, ys = [], []
    for poly in _as_polygons(geom):
        for ring in poly:
            for x, y in ring:
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def _as_polygons(geom):
    if geom is None:
        return []
    if geom["type"] == "Polygon":
        return [geom["coordinates"]]
    if geom["type"] == "MultiPolygon":
        return geom["coordinates"]
    return []


def centroid(geom):
    """Centroide por area (nao apenas do bbox)."""
    polys = _as_polygons(geom)
    cx = cy = tot = 0.0
    for poly in polys:
        ring = poly[0]
        a = signed_area(ring)
        if a == 0:
            continue
        sx = sy = 0.0
        for i in range(len(ring) - 1):
            x1, y1 = ring[i]
            x2, y2 = ring[i + 1]
            cross = x1 * y2 - x2 * y1
            sx += (x1 + x2) * cross
            sy += (y1 + y2) * cross
        cx += sx / (6 * a) * abs(a)
        cy += sy / (6 * a) * abs(a)
        tot += abs(a)
    if tot == 0:
        b = bbox(geom)
        return [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2] if b else None
    return [_r(cx / tot), _r(cy / tot)]


def point_in_ring(x, y, ring):
    """Ray casting. Fronteira conta como dentro apenas por acaso numerico."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y):
            xint = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < xint:
                inside = not inside
        j = i
    return inside


def point_in_geom(x, y, geom):
    for poly in _as_polygons(geom):
        if point_in_ring(x, y, poly[0]):
            if not any(point_in_ring(x, y, h) for h in poly[1:]):
                return True
    return False


class PolygonIndex:
    """
    Indice bbox + grade regular para ponto-em-poligono em lote.
    Com 44 zonas e 118 mil pontos, forca bruta seria 5,2 milhoes de testes;
    a grade reduz para poucas dezenas de milhares.
    """

    def __init__(self, features, cell=0.01):
        self.feats = features
        self.cell = cell
        self.boxes = [bbox(f["geometry"]) for f in features]
        self.grid = {}
        for idx, b in enumerate(self.boxes):
            if b is None:
                continue
            for gx in range(int(b[0] // cell), int(b[2] // cell) + 1):
                for gy in range(int(b[1] // cell), int(b[3] // cell) + 1):
                    self.grid.setdefault((gx, gy), []).append(idx)

    def find(self, x, y):
        """Devolve o indice da primeira feicao que contem (x, y), ou None."""
        for idx in self.grid.get((int(x // self.cell), int(y // self.cell)), ()):
            b = self.boxes[idx]
            if b[0] <= x <= b[2] and b[1] <= y <= b[3]:
                if point_in_geom(x, y, self.feats[idx]["geometry"]):
                    return idx
        return None


# ----------------------------------------------------------------------
# Saida
# ----------------------------------------------------------------------
def write_geojson(path, features, rotulo=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fc = {"type": "FeatureCollection", "features": features}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False, separators=(",", ":"))
    mb = os.path.getsize(path) / 1e6
    print(f"  -> {os.path.basename(path)}: {len(features):,} feicoes, {mb:.1f} MB"
          f"{' | ' + rotulo if rotulo else ''}")


def write_json(path, obj, compacto=False):
    """
    Escreve JSON. `compacto=True` remove a indentacao.

    O padrao e indentado porque quase todos os JSON daqui sao pequenos e
    lidos por gente (parametros, lei, stats). A excecao sao os arquivos com
    dezenas de milhares de registros: em enderecos.json a indentacao dobrava
    o arquivo — 6,2 MB contra 3,0 MB — em espaco em branco.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sep = (",", ":") if compacto else (",", ": ")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False,
                  indent=None if compacto else 1, separators=sep)
    print(f"  -> {os.path.basename(path)}: {os.path.getsize(path)/1000:.1f} kB")


def num_br(v, default=None):
    """Converte '6637960,16389' / '7,5' / 'n/a' / '10%' para float ou default."""
    if v is None:
        return default
    s = str(v).strip()
    if not s or s.lower() in ("n/a", "na", "-", "nan"):
        return default
    if s.endswith("%"):
        return default
    if "," in s and "." in s:                  # 1.234,56 -> ponto e milhar
        s = s.replace(".", "")
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return default

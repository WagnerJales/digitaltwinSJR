"""
Auditoria de qualidade dos dados processados.

Roda depois do pipeline e imprime um relatorio dos problemas encontrados na
base de origem. Serve para dois publicos: para nos, como teste de regressao
do pipeline; para a Prefeitura, como lista objetiva do que precisa ser
corrigido no arquivo de zoneamento.

    python pipeline/qa_dados.py

Sai com codigo 1 se encontrar inconsistencia que quebre o app (campo faltando,
sigla duplicada, geometria de tipo errado). Problemas da base de origem
(auto-interseccao, area divergente) sao reportados mas nao falham — sao
achados, nao bugs nossos.
"""
import json
import os
import sys

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
PROC = os.path.join(BASE, "data", "processados")

# campos que o app le diretamente em paint/filter ou no painel
OBRIGATORIOS = ["sigla", "nome", "cor", "familia", "familia_rotulo", "area_m2",
                "gabarito_max_pav", "edificacoes", "area_construida_m2",
                "domicilios", "ocupacao_observada_pct", "densidade_dom_ha"]


def carrega(nome):
    p = os.path.join(PROC, nome)
    if not os.path.exists(p):
        sys.exit(f"ERRO: falta {nome} — rode python pipeline/run_all.py")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _orient(a, b, c):
    v = (b[1] - a[1]) * (c[0] - b[0]) - (b[0] - a[0]) * (c[1] - b[1])
    return 0 if abs(v) < 1e-14 else (1 if v > 0 else 2)


def _cruza(p, p2, q, q2):
    return (_orient(p, p2, q) != _orient(p, p2, q2)
            and _orient(q, q2, p) != _orient(q, q2, p2))


def aneis(geom):
    if geom["type"] == "Polygon":
        return geom["coordinates"]
    return [r for poly in geom["coordinates"] for r in poly]


def auto_interseccoes(geom):
    total = 0
    for ring in aneis(geom):
        n = len(ring) - 1
        for i in range(n):
            for j in range(i + 2, n):
                if i == 0 and j == n - 1:
                    continue
                if _cruza(ring[i], ring[i + 1], ring[j], ring[j + 1]):
                    total += 1
    return total


def main():
    zon = carrega("zoneamento.geojson")
    par = carrega("parametros.json")
    feats = zon["features"]
    erros, achados = [], []

    # ---- consistencia interna (falha o build) ----
    siglas = set()
    for f in feats:
        p = f["properties"]
        s = p.get("sigla")
        for c in OBRIGATORIOS:
            if c not in p:
                erros.append(f"{s}: falta o campo '{c}'")
        if s in siglas:
            erros.append(f"sigla duplicada '{s}' — quebra o promoteId do MapLibre")
        siglas.add(s)
        if not isinstance(p.get("cor"), str) or not p["cor"].startswith("#"):
            erros.append(f"{s}: cor invalida {p.get('cor')!r}")
        if f["geometry"]["type"] not in ("Polygon", "MultiPolygon"):
            erros.append(f"{s}: geometria {f['geometry']['type']}")
    if set(par) != siglas:
        erros.append("parametros.json nao casa com zoneamento.geojson: "
                     f"{sorted(set(par) ^ siglas)}")

    # ---- achados na base de origem (nao falham) ----
    div = [(p["properties"]["sigla"], p["properties"]["area_m2"],
            p["properties"]["area_base_m2"], p["properties"]["divergencia_area_pct"])
           for p in feats if p["properties"].get("revisar_area")]

    topo = []
    for f in feats:
        n = auto_interseccoes(f["geometry"])
        if n:
            topo.append((f["properties"]["sigla"], n))

    sem_gab = [f["properties"]["sigla"] for f in feats
               if not f["properties"].get("gabarito_max_pav")]

    vazias = [f["properties"]["sigla"] for f in feats
              if not f["properties"].get("edificacoes")]

    # ---- relatorio ----
    print("=" * 70)
    print("QA DOS DADOS — Gemeo Digital SJR")
    print("=" * 70)
    print(f"\n{len(feats)} zonas | {len(par)} entradas em parametros.json")

    print(f"\n[1] Area do poligono divergente do atributo da base: {len(div)} zonas")
    for s, a, b, d in sorted(div, key=lambda x: -abs(x[3])):
        print(f"    {s:<18} geometria {a/1e6:7.2f} km2 | base {b/1e6:7.2f} km2 "
              f"| {d:+6.1f}%")

    print(f"\n[2] Aneis auto-interceptantes (geometria invalida pela OGC): "
          f"{len(topo)} zonas")
    for s, n in sorted(topo, key=lambda x: -x[1]):
        print(f"    {s:<18} {n} cruzamento(s)")

    print(f"\n[3] Sem gabarito definido: {len(sem_gab)} zonas")
    print("    " + ", ".join(sem_gab))

    print(f"\n[4] Sem nenhuma edificacao detectada: {len(vazias)} zonas")
    print("    " + (", ".join(vazias) if vazias else "(nenhuma)"))

    if erros:
        print(f"\n{'='*70}\nERROS QUE QUEBRAM O APP: {len(erros)}")
        for e in erros:
            print(f"  - {e}")
        sys.exit(1)
    print(f"\n{'='*70}")
    print("Consistencia interna: OK. Os itens acima sao achados da base de")
    print("origem — cabe a Prefeitura corrigi-los no arquivo de zoneamento.")


if __name__ == "__main__":
    main()

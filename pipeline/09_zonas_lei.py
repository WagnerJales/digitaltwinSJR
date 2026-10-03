"""
Zoneamento a partir da LEI, nao do KMZ.

Le os memoriais descritivos do Anexo III - Tabela 1 da Lei Complementar
77/2025 (autografo da Camara, leis/LC_77_AUTOGRAFO.pdf), converte as
coordenadas UTM 23S / SIRGAS 2000 para WGS84 e escreve o zoneamento oficial.

Por que isto substitui o KMZ: o KMZ traz 44 zonas de outra versao do
zoneamento, cujas siglas nao constam da lei. A lei sancionada descreve
13 poligonos por coordenada, vertice a vertice. Sao esses os limites legais.

Saidas:
    data/processados/zoneamento.geojson   13 zonas com geometria da lei
    data/processados/parametros.json      Tabela 7 por sigla
    data/processados/zonas_qa.json        auditoria da extracao

Roda com stdlib + pypdf.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_geo as G

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = os.path.join(BASE, "leis", "LC_77_AUTOGRAFO.pdf")
PROC = os.path.join(BASE, "data", "processados")

# ---------------------------------------------------------------------------
# Como o memorial nomeia cada zona x sigla da Tabela 1.
# O texto da lei nao e uniforme (ZRBJJ aparece como "BOM JARDIM", ZRI como
# "ITAPARI" no memorial e "ITAPAI" na Tabela 7), entao o vinculo e explicito.
# ---------------------------------------------------------------------------
MEMORIAIS = {
    "ZONA RURAL BOM JARDIM":                    ("ZRBJJ", "rural"),
    "ZONA RURAL MATA/SANTANA":                  ("ZRMS",  "rural"),
    "ZONA RURAL DO ITAPARI":                    ("ZRI",   "rural"),
    "ZONA RURAL DE GUARAPIRANGA":               ("ZRG",   "rural"),
    "ZONA CENTRAL":                             ("ZC",    "urbana"),
    "ZONA SEDE":                                ("ZS",    "urbana"),
    "ZDU ARACAGI":                              ("ZDU - A",  "urbana"),
    "ZDU BOA VIAGEM":                           ("ZDU - BV", "urbana"),
    "ZONA DE DESENVOLVIMENTO URBANO - PANAQUATIRA": ("ZDU - P", "urbana"),
    "ZONA DE EXPANSAO URBANA - ZEU":            ("ZEU",   "urbana"),
    "PARQUE DA QUINTA":                         ("PARQUE DA QUINTA", "ambiental"),
    "ZONA DE PRESERVACAO DA APA DE SAO PAULO":  ("ZPA SAO PAULO",    "ambiental"),
    "ZPA J":                                    ("ZPA JENIPARANA",   "ambiental"),
}

CORES = {
    "urbana":    "#f2a65a",
    "rural":     "#a8c686",
    "ambiental": "#4c9a72",
}

# Vertice: "Pt0 598189.83 9712797.27 Pt0-Pt1 101 18'35.76'' ... 226.65"
#
# Casamos sobre o texto ACHATADO, nao linha a linha: o extrator de texto do
# PDF as vezes parte a linha em pedacos ("Pt257" sozinho, coordenadas depois),
# e a leitura por linha perde esses vertices em silencio.
# O lookbehind evita casar o "Pt257" que aparece dentro do rotulo do lado
# "Pt256-Pt257". As faixas de digitos sao as do UTM 23S nesta latitude
# (E com 6 digitos, N com 7 comecando em 9), o que descarta azimute e
# distancia, que tem magnitude bem menor.
RE_VERTICE = re.compile(r"(?<![-\d])Pt(\d+)\s+(\d{6}\.\d{2})\s+(9\d{6}\.\d{2})(?!\d)")
RE_MEMORIAL = re.compile(r"MEMORIAL DESCRITIVO\s*[–—-]?\s*(.+)")


def _sem_acento(s):
    tab = str.maketrans("ÁÀÂÃÉÊÍÓÔÕÚÇáàâãéêíóôõúç",
                        "AAAAEEIOOOUCaaaaeeiooouc")
    return s.translate(tab)


def _titulo_memorial(linha):
    m = RE_MEMORIAL.search(linha)
    if not m:
        return None
    t = _sem_acento(m.group(1)).upper()
    t = re.sub(r"\s+", " ", t).strip(" -–")
    return t


def _texto_por_memorial(reader):
    """Fatia o PDF em blocos de texto, um por memorial descritivo."""
    blocos, ordem, atual = {}, [], None
    for pagina in reader.pages:
        for linha in (pagina.extract_text() or "").splitlines():
            titulo = _titulo_memorial(linha.strip())
            if titulo and titulo in MEMORIAIS:
                if titulo not in blocos:
                    blocos[titulo] = []
                    ordem.append(titulo)
                atual = titulo
                continue
            if atual is not None:
                blocos[atual].append(linha)
    return ordem, {t: " ".join(ls) for t, ls in blocos.items()}


def extrai_memoriais(reader):
    """Le os vertices de cada memorial, agrupados em aneis.

    Cada vertice traz seu proprio indice Pt, e e por ele que indexamos: e o
    unico jeito de saber que nada se perdeu. Um memorial pode descrever mais
    de um anel; quando isso acontece a numeracao reinicia em Pt0.
    """
    ordem, blocos = _texto_por_memorial(reader)
    zonas = {}          # titulo -> lista de aneis, cada anel = lista de (E, N)
    for titulo in ordem:
        aneis, corrente, ultimo = [], {}, -1
        for m in RE_VERTICE.finditer(blocos[titulo]):
            i = int(m.group(1))
            if i <= ultimo:                 # numeracao reiniciou: outro anel
                aneis.append(corrente)
                corrente = {}
            ponto = (float(m.group(2)), float(m.group(3)))
            if i in corrente and corrente[i] != ponto:
                raise SystemExit(f"ERRO: {titulo} Pt{i} com dois valores.")
            corrente[i] = ponto
            ultimo = i
        if corrente:
            aneis.append(corrente)

        saida = []
        for k, anel in enumerate(aneis):
            faltam = sorted(set(range(max(anel) + 1)) - set(anel))
            if faltam:
                raise SystemExit(
                    f"ERRO: {titulo} anel {k}: faltam Pt{faltam[:20]} "
                    f"de Pt0..Pt{max(anel)}.")
            saida.append([anel[i] for i in range(len(anel))])
        zonas[titulo] = saida
    return ordem, zonas


def extrai_tabela7(reader):
    """Le a Tabela 7 (parametros por zona) direto do PDF."""
    alvo = None
    for p in reader.pages:
        t = p.extract_text() or ""
        u = _sem_acento(t).upper()
        if "TABELA 7" in u and "PARAMETROS URBANOS" in u:
            alvo = t
    if alvo is None:
        raise SystemExit("ERRO: Tabela 7 nao encontrada no PDF.")

    # As celulas quebram em varias linhas; achatamos e procuramos, para cada
    # sigla, a sequencia "area  testada  ATME  ALML  altura".
    txt = re.sub(r"\s+", " ", alvo)
    num = r"(\d{1,4}(?:[.,]\d+)?)"
    padrao = re.compile(
        r"\b(ZS|ZDU\s*[-–]\s*A|ZDU\s*[-–]\s*BV|ZDU\s*[-–]\s*P|"
        r"ZEU|ZC|ZRMS|ZRI|ZRBJJ|ZRG)\b[^0-9]*"
        + num + r"\s+" + num + r"\s+" + num + r"\s+" + num + r"\s+" + num)

    achados = {}
    for m in padrao.finditer(txt):
        sigla = re.sub(r"\s*[-–]\s*", " - ", m.group(1).strip())
        vals = [G.num_br(m.group(i)) for i in range(2, 7)]
        achados[sigla] = {
            "area_min_m2":   vals[0],
            "testada_min_m": vals[1],
            "atme_pct":      vals[2],
            "alml_pct":      vals[3],
            "altura_max_m":  vals[4],
        }
    return achados


def main():
    try:
        from pypdf import PdfReader
    except ImportError:
        raise SystemExit("ERRO: falta o pypdf.  pip install pypdf")
    if not os.path.exists(PDF):
        raise SystemExit(f"ERRO: nao achei {PDF}")

    print("ZONEAMENTO PELA LEI (memoriais do Anexo III - Tabela 1)")
    reader = PdfReader(PDF)
    ordem, brutos = extrai_memoriais(reader)
    tab7 = extrai_tabela7(reader)

    faltando = [t for t in MEMORIAIS if t not in brutos]
    if faltando:
        raise SystemExit("ERRO: memoriais nao encontrados: "
                         + ", ".join(sorted(faltando)))

    feats, qa = [], []
    for titulo in ordem:
        sigla, familia = MEMORIAIS[titulo]
        aneis_utm = brutos[titulo]

        polis, brutos_pts, degenerados = [], 0, 0
        for utm in aneis_utm:
            brutos_pts += len(utm)
            # Alguns memoriais repetem a mesma coordenada em Pt seguidos
            # (lado de comprimento zero). Sao validos como texto, mas dao
            # vertice duplicado na geometria; removemos e contamos.
            limpo = [p for i, p in enumerate(utm) if i == 0 or p != utm[i - 1]]
            degenerados += len(utm) - len(limpo)
            if len(limpo) < 3:
                raise SystemExit(f"ERRO: {sigla} com anel de {len(limpo)} pts.")

            # O memorial nao repete o Pt0 no fim: o fechamento vem do ultimo
            # LADO (PtN-Pt0). Fechamos explicitamente.
            if limpo[0] != limpo[-1]:
                limpo = limpo + [limpo[0]]

            anel = [list(G.utm_para_wgs84(e, n)) for e, n in limpo]
            # Os memoriais descrevem o perimetro no sentido horario; o RFC
            # 7946 pede anel externo anti-horario, e o motor de viabilidade
            # depende disso para a normal esquerda apontar para dentro.
            if G.signed_area(anel) < 0:
                anel.reverse()
            polis.append(([anel], limpo))

        if len(polis) == 1:
            geom = {"type": "Polygon", "coordinates": polis[0][0]}
        else:
            geom = {"type": "MultiPolygon",
                    "coordinates": [p[0] for p in polis]}

        area_geo = G.area_m2(geom)
        area_utm = sum(G.area_utm_m2(p[1][:-1]) for p in polis)
        dif = abs(area_geo - area_utm) / area_utm * 100 if area_utm else 0.0
        utm = [p for anel in aneis_utm for p in anel]

        p = tab7.get(sigla, {})
        props = {
            "sigla": sigla,
            "nome": titulo.title(),
            "familia": familia,
            "cor": CORES[familia],
            "fonte": "LC 77/2025, Anexo III - Tabela 1 (memorial descritivo)",
            "vertices": brutos_pts,
            "aneis": len(polis),
            "area_m2": round(area_geo, 1),
            "area_ha": round(area_geo / 10000.0, 2),
            "area_km2": round(area_geo / 1e6, 3),
            "na_tabela7": sigla in tab7,
        }
        props.update({k: p.get(k) for k in
                      ("area_min_m2", "testada_min_m", "atme_pct",
                       "alml_pct", "altura_max_m")})
        if p:
            props["taxa_ocupacao_max_pct"] = round(100 - p["alml_pct"], 1)
            props["coef_aproveitamento"] = round(p["atme_pct"] / 100.0, 2)

        feats.append({"type": "Feature", "properties": props,
                      "geometry": geom})
        qa.append({"sigla": sigla, "vertices": brutos_pts,
                   "aneis": len(polis),
                   "vertices_degenerados": degenerados,
                   "area_utm_m2": round(area_utm, 1),
                   "area_wgs84_m2": round(area_geo, 1),
                   "divergencia_pct": round(dif, 4),
                   "na_tabela7": sigla in tab7})
        extra = f"  {degenerados} vert. degenerado(s)" if degenerados else ""
        print(f"  {sigla:<16} {brutos_pts:>4} vert  {len(polis)} anel(is)  "
              f"{area_geo/1e6:>8.3f} km2   "
              f"{'Tabela 7 OK' if sigla in tab7 else 'SEM Tabela 7'}{extra}")

    G.write_geojson(os.path.join(PROC, "zoneamento.geojson"), feats,
                    "zoneamento (LC 77/2025)")

    params = {}
    for f in feats:
        pr = f["properties"]
        params[pr["sigla"]] = {k: pr.get(k) for k in (
            "sigla", "nome", "familia", "cor", "area_m2", "area_ha",
            "area_km2", "area_min_m2", "testada_min_m", "atme_pct",
            "alml_pct", "altura_max_m", "taxa_ocupacao_max_pct",
            "coef_aproveitamento", "na_tabela7", "vertices")}
    G.write_json(os.path.join(PROC, "parametros.json"), params)
    G.write_json(os.path.join(PROC, "zonas_qa.json"),
                 {"fonte": os.path.basename(PDF), "zonas": qa,
                  "tabela7_lida": tab7})

    total = sum(f["properties"]["area_m2"] for f in feats) / 1e6
    sem7 = [f["properties"]["sigla"] for f in feats
            if not f["properties"]["na_tabela7"]]
    print(f"\n  {len(feats)} zonas | area somada {total:.1f} km2")
    print(f"  Tabela 7 lida do PDF: {len(tab7)} zonas")
    if sem7:
        print(f"  Sem parametros na Tabela 7 ({len(sem7)}): {', '.join(sem7)}")
    faltam_geom = [s for s in tab7 if s not in params]
    if faltam_geom:
        print(f"  Na Tabela 7 mas sem memorial: {', '.join(faltam_geom)}")


if __name__ == "__main__":
    main()

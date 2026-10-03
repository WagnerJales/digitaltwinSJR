"""
Gera dist/SJR-Geo.html — o app com os dados embutidos, que abre
direto no navegador (duplo clique), sem servidor local.

Precisa de internet apenas para o basemap e a biblioteca MapLibre (CDN).
"""
import json
import os
import sys

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
PROC = os.path.join(BASE, "data", "processados")

# nome -> arquivo. Os enderecos nao sao GeoJSON: 118 mil pontos em
# FeatureCollection custam 14,5 MB contra 2,9 MB no formato compacto, que o
# cliente expande no carregamento (expandeEnderecos em web/index.html).
CAMADAS = {
    "zoneamento":  "zoneamento.geojson",
    "edificacoes": "edificacoes.geojson",
    "vias":        "vias.geojson",
    "enderecos":   "enderecos.json",
    "setores":     "setores.geojson",
}
MARCADOR = "<script>\n/* ========="


def main():
    embed = {}
    faltando = []
    for nome, arq in CAMADAS.items():
        p = os.path.join(PROC, arq)
        if not os.path.exists(p):
            faltando.append(arq)
            continue
        with open(p, encoding="utf-8") as f:
            embed[nome] = json.load(f)
    pp = os.path.join(PROC, "parametros.json")
    if not os.path.exists(pp):
        faltando.append("parametros.json")
    else:
        with open(pp, encoding="utf-8") as f:
            embed["parametros"] = json.load(f)
    # metadados do recorte das edificacoes — o cliente desenha o limite
    ep = os.path.join(PROC, "stats_edificacoes.json")
    if os.path.exists(ep):
        with open(ep, encoding="utf-8") as f:
            embed["stats_edificacoes"] = json.load(f)
    lp = os.path.join(PROC, "lei.json")
    if not os.path.exists(lp):
        faltando.append("lei.json")
    else:
        with open(lp, encoding="utf-8") as f:
            embed["lei"] = json.load(f)
    if faltando:
        sys.exit("ERRO: rode o pipeline antes. Faltando: " + ", ".join(faltando))

    src = os.path.join(BASE, "web", "index.html")
    with open(src, encoding="utf-8") as f:
        html = f.read()

    # A substituicao depende do texto exato do index.html — inclusive das
    # quebras de linha. Se um editor salvar em CRLF, o replace silenciosamente
    # nao casa e o arquivo sai SEM dados. Normalizamos e conferimos.
    html = html.replace("\r\n", "\n")
    if MARCADOR not in html:
        sys.exit(f"ERRO: nao achei o marcador {MARCADOR!r} em web/index.html — "
                 "o gerador precisa ser ajustado.")

    inject = ("<script>window.__EMBED = "
              + json.dumps(embed, ensure_ascii=False, separators=(",", ":"))
              + ";</script>\n<script>\n/* =========")
    saida = html.replace(MARCADOR, inject, 1)
    if saida == html:
        sys.exit("ERRO: a injecao nao alterou o HTML.")
    if "window.__EMBED = " not in saida:
        sys.exit("ERRO: dados nao foram embutidos.")

    out = os.path.join(BASE, "dist", "SJR-Geo.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(saida)
    tam = os.path.getsize(out) / 1e6
    print(f"ok -> {out} ({tam:.1f} MB)")
    for k, v in embed.items():
        if isinstance(v, dict):
            n = len(v.get("features", v.get("pontos", v)))
        else:
            n = len(v)
        print(f"     {k}: {n:,} {'feicoes' if k in CAMADAS else 'zonas'}")
    if tam > 25:
        print("AVISO: arquivo grande; navegadores antigos podem demorar a abrir.")


if __name__ == "__main__":
    main()

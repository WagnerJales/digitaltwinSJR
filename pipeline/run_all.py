"""
Roda o pipeline inteiro a partir dos dados reais em SIG/.

    python pipeline/run_all.py                 # recorte do nucleo urbano (demo)
    python pipeline/run_all.py --completo      # + edificacoes do municipio inteiro
                                               #   (para tippecanoe/PMTiles)

Nao requer nenhuma dependencia externa — so a stdlib do Python 3.
"""
import importlib.util
import os
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
ETAPAS = [
    ("09_zonas_lei.py", "Zoneamento pelos memoriais da LC 77/2025"),
    ("11_vias.py", "Malha viaria (OSM)"),
    ("12_edificacoes.py", "Edificacoes (Google Open Buildings)"),
    ("13_enderecos.py", "Enderecos (CNEFE 2022)"),
    ("13b_setores.py", "Setores censitarios (Censo 2022, IBGE)"),
    ("14_consolidar.py", "Consolidacao dos indicadores"),
    ("16_leis.py", "Parametros da LC 77/2025 + conferencia da cobertura"),
    ("gerar_standalone.py", "HTML standalone com dados embutidos"),
]


def carregar(arquivo):
    spec = importlib.util.spec_from_file_location(
        arquivo.replace(".py", ""), os.path.join(BASE, arquivo))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    completo = "--completo" in sys.argv
    t0 = time.time()
    for i, (arquivo, desc) in enumerate(ETAPAS, 1):
        print(f"\n[{i}/{len(ETAPAS)}] {desc}")
        print("-" * 68)
        mod = carregar(arquivo)
        if arquivo == "12_edificacoes.py":
            mod.main(completo=completo)
        else:
            mod.main()
    print(f"\nPipeline concluido em {time.time()-t0:.0f}s.")
    print("Abra dist/SJR-Geo.html ou rode:")
    print("  python -m http.server 8080   ->   http://localhost:8080/web/")


if __name__ == "__main__":
    main()

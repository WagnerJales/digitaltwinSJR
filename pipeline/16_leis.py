"""
Parâmetros da LEI COMPLEMENTAR Nº 77, DE 10 DE JULHO DE 2025
(zoneamento, parcelamento, uso e ocupação do solo urbano de São José de Ribamar)

Entrada : leis/LC_77_AUTOGRAFO.pdf   (271 p., autógrafo da Câmara, com anexos)
Saída   : data/processados/lei.json

As tabelas do Anexo III estão transcritas abaixo a partir do autógrafo
(Tabela 7 na p. 267, Tabela 8 na p. 268). O script relê o PDF para CONFERIR a
transcrição — se o texto de origem mudar, ele avisa em vez de seguir com
número velho.

O zoneamento georreferenciado vem dos memoriais descritivos do mesmo PDF
(09_zonas_lei.py). Lei e geometria passaram a ter uma única fonte, então aqui
o cruzamento é 1:1 e o que se verifica é a COBERTURA: toda zona com geometria
tem parâmetro, e todo parâmetro tem geometria.

O ZONEAMENTO_RIBAMAR.kmz foi descartado: trazia 44 zonas de outra versão do
zoneamento, com siglas que não constam da lei.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_geo import write_json

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
PROC = os.path.join(BASE, "data", "processados")
LEIS = os.path.join(BASE, "leis")
PDF = os.path.join(LEIS, "LC_77_AUTOGRAFO.pdf")

LEI = {
    "norma": "Lei Complementar nº 77, de 10 de julho de 2025",
    "ementa": ("Dispõe sobre o zoneamento, parcelamento, uso e ocupação do "
               "solo urbano de São José de Ribamar e dá outras providências."),
    "fonte": "Autógrafo da Câmara Municipal de São José de Ribamar (271 p.)",
    "publicacao": "Diário Oficial do Município nº 2.035/2025, de 15/07/2025",
    "plano_diretor": "Lei Complementar nº 57, de 08 de outubro de 2020",
}

# ---------------------------------------------------------------------------
# ANEXO III — TABELA 7: Parâmetros Urbanos de Ocupação das Zonas (p. 267)
#   area_min_m2   área mínima do lote
#   testada_min_m testada mínima
#   atme_pct      Área Total Máxima de Edificação: razão máxima entre área
#                 construída e área do terreno (glossário XVII). É o
#                 coeficiente de aproveitamento, em percentual.
#   alml_pct      Área Livre Mínima do Lote: espaço descoberto, livre de
#                 edificações (glossário XVIII). Taxa de ocupação máxima
#                 = 100 - alml_pct.
#   altura_max_m  altura máxima da edificação, em METROS (art. 107)
#
# São 10 zonas com parâmetro: 6 urbanas e 4 rurais. As duas zonas de proteção
# ambiental da Tabela 1 (ZPA São Paulo e ZPA Jeniparana) não têm linha aqui —
# aparecem só na Tabela 6.2, de adequação de usos.
# ---------------------------------------------------------------------------
TABELA_7 = {
    "ZS":      ("Zona da Sede",                                "urbana", 150.0,  7.5, 240, 30, 30),
    "ZC":      ("Zona Central",                                "urbana", 150.0,  7.5, 240, 30, 15),
    "ZEU":     ("Zona de Expansão Urbana",                     "urbana", 150.0,  7.5, 360, 30, 60),
    "ZDU - A": ("Zona de Desenvolvimento Urbano - Araçagi",    "urbana", 150.0,  7.5, 370, 40, 90),
    "ZDU - BV":("Zona de Desenvolvimento Urbano - Boa Viagem", "urbana", 150.0,  7.5, 370, 40, 90),
    "ZDU - P": ("Zona de Desenvolvimento Urbano - Panaquatira","urbana", 150.0,  7.5, 370, 40, 90),
    "ZRMS":    ("Zona Rural Mata/Santana",                     "rural",  200.0, 10.0, 360, 30, 60),
    "ZRI":     ("Zona Rural Itaparí",                          "rural",  200.0, 10.0, 180, 40, 60),
    "ZRBJJ":   ("Zona Rural Bom Jardim/Juçatuba",              "rural",  200.0, 10.0, 180, 40, 60),
    "ZRG":     ("Zona Rural Guarapiranga",                     "rural",  200.0, 10.0, 180, 40, 60),
}

# Zonas da Tabela 1 sem linha na Tabela 7.
SEM_PARAMETRO = {
    "ZPA SAO PAULO":    "Zona de Proteção Ambiental São Paulo",
    "ZPA JENIPARANA":   "Zona de Proteção Ambiental Jeniparana",
    "PARQUE DA QUINTA": "Parque da Quinta",
}

# ---------------------------------------------------------------------------
# ANEXO III — TABELA 8: Afastamentos (p. 268)
# Os afastamentos dependem do GABARITO (nº de pavimentos), não da zona.
# (gab_min, gab_max, frontal_m, lateral_m, fundos_m)
#
# Acima de 5 pavimentos a tabela grafa "*" em lateral e fundos, com a nota
# "Ver incisos II, III e IV" — que remetem ao art. 111. Por isso lateral e
# fundos entram como None: o valor é calculado, não tabelado.
# ---------------------------------------------------------------------------
TABELA_8 = [
    (1,  1,  5.0,  1.5,  1.5),
    (2,  2,  5.0,  2.0,  1.5),
    (3,  5,  5.0,  3.0,  3.0),
    (6,  10,  6.0, None, None),
    (11, 20,  8.0, None, None),
    (21, 30, 10.0, None, None),
]

# Art. 111, incisos II a IV: acréscimo por pavimento contado a partir do
# quinto, sobre o afastamento estabelecido na Tabela 8.
# (gab_min, gab_max, acrescimo_m, inciso)
ACRESCIMO_ART111 = [
    (6,  10, 0.65, "II"),
    (11, 20, 0.55, "III"),
    (21, 30, 0.45, "IV"),
]
BASE_LATERAL_ART111 = 3.0    # último valor tabelado (gabarito 3 a 5)

# Pontos em que o texto da lei não fecha. O app mostra estas ressalvas em vez
# de escolher em silêncio; não são opinião nossa sobre o mérito, são o que
# está escrito.
RESSALVAS_TABELA_8 = [
    {"assunto": "base do afastamento lateral/fundos acima de 5 pavimentos",
     "texto": ("A Tabela 8 grafa '*' em lateral e fundos a partir do 6º "
               "pavimento e remete aos incisos II a IV do art. 111, que mandam "
               "acrescer 0,65 / 0,55 / 0,45 m por pavimento 'ao afastamento "
               "estabelecido no Anexo 8'. O último valor tabelado para lateral "
               "e fundos é 3,00 m (gabarito 3 a 5), e é essa a base adotada "
               "aqui. O frontal é lido direto da tabela (6, 8 ou 10 m), sem "
               "acréscimo, porque a nota '*' só marca as células de lateral e "
               "fundos."),
     "efeito": "Confirmar com a SEMREC antes de uso para aprovação."},
    {"assunto": "descontinuidade no 21º pavimento",
     "texto": ("Pelo art. 111, o afastamento lateral cresce até 11,25 m no 20º "
               "pavimento (3,00 + 15 x 0,55) e cai para 10,20 m no 21º "
               "(3,00 + 16 x 0,45), porque o acréscimo por pavimento diminui. "
               "A regra está aplicada como escrita."),
     "efeito": "Um prédio de 21 pavimentos exige menos afastamento que um de 20."},
    {"assunto": "gabarito acima de 30 pavimentos",
     "texto": ("A Tabela 8 e o art. 111 param no 30º pavimento. Acima disso a "
               "lei não define afastamento."),
     "efeito": ("Nas ZDU (90 m de altura máxima) o gabarito para em 30 "
                "pavimentos por falta de parâmetro, não por vedação.")},
]

# ---------------------------------------------------------------------------
# Regras gerais, com o artigo de origem — o app cita a fonte de cada número.
# ---------------------------------------------------------------------------
REGRAS = {
    "taxa_permeabilidade_pct": {
        "valor": 20,
        "artigo": "Art. 98",
        "texto": ("A Taxa de Permeabilidade deverá ser de 20% (vinte por cento) "
                  "da área do terreno, em todas as zonas."),
    },
    "alml_permeavel_pct": {
        "valor": 50,
        "artigo": "Art. 106, parágrafo único",
        "texto": ("É obrigatório que pelo menos 50% da ALML do lote seja de "
                  "área 100% permeável."),
    },
    "pe_direito_min_m": {
        "valor": 2.60,
        "artigo": "Art. 109",
        "texto": ("O pé-direito mínimo permitido é de 2,60m, admitindo-se "
                  "2,30m nos banheiros e circulações."),
    },
    "pavimentos_livres": {
        "valor": True,
        "artigo": "Art. 114",
        "texto": ("O número de pavimentos de uma edificação é livre desde que "
                  "não ultrapasse a altura máxima permitida pela zona."),
    },
    "afastamento_frontal_por_testada": {
        "valor": True,
        "artigo": "Art. 112",
        "texto": ("Nos lotes que possuam mais de um limite voltado, com ou sem "
                  "acesso, à via pública possuirão tantos quantos forem os "
                  "afastamentos frontais."),
    },
    "frente_pelo_acesso": {
        "valor": True,
        "artigo": "Art. 108",
        "texto": ("O lote que possuir 2 ou mais limites voltados para "
                  "diferentes vias, o acesso principal do lote determinará a "
                  "sua frente."),
    },
    "altura_pela_maior_testada": {
        "valor": True,
        "artigo": "Art. 107, I",
        "texto": ("Quando um imóvel fizer frente para duas ou mais vias, a "
                  "altura máxima será medida a partir do passeio "
                  "correspondente à testada de maior dimensão."),
    },
    "lateral_ocupavel_ate_9m": {
        "valor": 9.0,
        "artigo": "Art. 115",
        "texto": ("A edificação poderá ocupar um dos afastamentos laterais "
                  "desde que não haja aberturas voltadas para os lotes "
                  "vizinhos e não ultrapasse 9,00m de altura."),
    },
    "podio_5_pav_uso_comum": {
        "valor": 5,
        "artigo": "Art. 111, § 2º",
        "texto": ("Nas edificações acima de 5 pavimentos, serão admitidos "
                  "afastamentos diferenciados quando os 5 primeiros pavimentos "
                  "sejam de uso comum da edificação, seguindo a Tabela 8."),
    },
    "reducao_lateral_50pct": {
        "valor": 50,
        "artigo": "Art. 116",
        "texto": ("Os afastamentos laterais obrigatórios poderão sofrer redução "
                  "de até 50%, numa extensão máxima de 1/3 da profundidade do "
                  "lote, desde que ocupados por escadas, elevadores, rampas, "
                  "lixeiras e circulações comunitárias."),
    },
    "subsolo_afastamento_frontal_m": {
        "valor": 5.0,
        "artigo": "Art. 118",
        "texto": ("Será permitida a construção de subsolos, respeitada a taxa "
                  "de permeabilidade e o afastamento mínimo frontal de 5,00m."),
    },
    "elevador_acima_5_pav": {
        "valor": 5,
        "artigo": "Art. 110",
        "texto": ("Edificações com mais de 5 pavimentos ou 12,00m de desnível "
                  "exigem no mínimo 1 elevador; acima de 10 pavimentos, 2."),
    },
    "rural_afastamento_vizinho_m": {
        "valor": 3.0,
        "artigo": "Art. 113",
        "texto": ("Nas zonas rurais, não será permitido edificações a menos de "
                  "3,00m do terreno vizinho."),
    },
    "terreo_alto_conta_gabarito_m": {
        "valor": 3.0,
        "artigo": "Art. 111, § 1º",
        "texto": ("Na hipótese de uma edificação térrea possuir o pavimento "
                  "superior a 6,00m, será considerada a cada 3,00m um "
                  "gabarito, para cálculo dos afastamentos."),
    },
    "zona_de_maior_insercao": {
        "valor": True,
        "artigo": "Art. 81 e Art. 83",
        "texto": ("A ocupação de lote situado em duas ou mais Zonas observará "
                  "as exigências definidas para a Zona de maior percentagem de "
                  "inserção na sua área."),
    },
}

# ---------------------------------------------------------------------------
# ARTS. 100 a 105 — a ÚNICA via pela qual a área construída supera a ATME.
#
# Não é desconto em função do gabarito: a ATME é percentual fixo da área do
# lote, igual para 2 ou para 20 pavimentos. O que a lei faz é retirar da
# CONTA certas áreas, em função do uso do pavimento. A área computável
# continua limitada à ATME; a área construída total pode passar.
#
# "modelavel" marca as exclusões que o app consegue representar como pavimento
# inteiro no bloco 3D. As demais (circulação, áreas comuns, beirais) são
# frações internas de cada laje — modelá-las como percentual arbitrado
# inflaria a área construída sem respaldo em projeto.
# ---------------------------------------------------------------------------
EXCLUSOES_ATME = [
    {"artigo": "Art. 100", "chave": "cobertura", "modelavel": True,
     "texto": ("Nas edificações que possuam unidades habitacionais ou "
               "comerciais no pavimento de cobertura, não serão estes "
               "computados na ATME."),
     "condicoes": ["não ultrapassar a altura máxima da zona",
                   "área construída de até 50% da laje"],
     "fracao_laje": 0.50},
    {"artigo": "Art. 101", "chave": "garagem", "modelavel": True,
     "texto": ("Os pavimentos destinados ao uso exclusivo de garagem não "
               "serão computados como ATME."),
     "condicoes": ["não ultrapassar a altura máxima permitida pela zona"]},
    {"artigo": "Art. 105", "chave": "pilotis", "modelavel": True,
     "texto": ("Os pilotis não serão computados na ATME, mas computarão na "
               "altura máxima da edificação."),
     "condicoes": ["computa na altura máxima da edificação"]},
    {"artigo": "Art. 102", "chave": "circulacao", "modelavel": False,
     "texto": ("As áreas de circulação vertical e horizontal (escadas, rampas "
               "e elevadores) não serão computadas na ATME."),
     "condicoes": []},
    {"artigo": "Art. 103", "chave": "uso_comum", "modelavel": False,
     "texto": ("As áreas de uso comum (recepções, salão de festas, piscina, "
               "guarita, entre outros) não serão computadas na ATME."),
     "condicoes": []},
    {"artigo": "Art. 104", "chave": "elementos", "modelavel": False,
     "texto": ("Pergolados, jardineiras, jardim de inverno, beirais, shafts e "
               "dutos de ventilação e/ou iluminação não serão computados na "
               "ATME."),
     "condicoes": []},
]

# ---------------------------------------------------------------------------
# O que a LC 77/2025 NÃO tem. Registrado porque a ausência é informação: sem
# isso, quem consulta supõe que existe um caminho de compra de potencial —
# e não existe. Verificado por busca no texto integral do autógrafo.
# ---------------------------------------------------------------------------
INSTRUMENTOS_AUSENTES = {
    "solo_criado": ("Não há 'solo criado' na LC 77/2025: zero ocorrências no "
                    "texto. A lei não separa coeficiente básico de "
                    "coeficiente máximo — a ATME é teto único por zona."),
    "outorga_onerosa": ("Não há outorga onerosa do direito de construir: zero "
                        "ocorrências de 'outorga' e de 'onerosa'."),
    "transferencia": ("Não há transferência do direito de construir."),
    "consequencia": ("A ATME não é comprável nem transferível. A área "
                     "construída só supera a ATME pelas exclusões dos arts. "
                     "100 a 105, que dependem do USO do pavimento, não de "
                     "contrapartida. Instrumentos de flexibilização, se "
                     "existirem, estarão no Plano Diretor (LC 57/2020), que "
                     "não integra esta base."),
}

# ---------------------------------------------------------------------------
# EM QUE CONDIÇÕES A LEI ADMITE AFASTAR-SE DOS ÍNDICES DA TABELA 7
#
# Busca no texto integral do autógrafo: são DUAS hipóteses, e só uma delas
# alcança a ALML. Fora daí, ATME e ALML são fixos por zona — não há outorga,
# não há solo criado, não há redução negociada.
# ---------------------------------------------------------------------------
ALTERACAO_INDICES = {
    "regularizacao_fundiaria": {
        "artigo": "Art. 117",
        "rotulo": "Reforma em lote de Regularização Fundiária",
        "texto": ("Para reformas em lotes oriundos de Regularização Fundiária "
                  "ficam dispensados o atendimento aos índices urbanísticos, "
                  "com exceção da taxa de permeabilidade e altura máxima da "
                  "edificação."),
        "atinge_alml": True,
        "dispensa": ["ALML (taxa de ocupação)", "ATME",
                     "área mínima do lote", "testada mínima"],
        "mantem": ["taxa de permeabilidade de 20% (Art. 98)",
                   "altura máxima da zona (Tabela 7)"],
        "condicoes": ["vale só para REFORMA, não para construção nova",
                      "o lote tem de ser oriundo de Regularização Fundiária"],
        "ambiguidade": (
            "A lei não define o que são 'índices urbanísticos'. O art. 97 "
            "arrola entre os parâmetros urbanos de ocupação também os "
            "AFASTAMENTOS. O app mantém os afastamentos aplicados — leitura "
            "conservadora — e dispensa apenas ALML, ATME e as dimensões "
            "mínimas do lote. A extensão da dispensa é decisão da SEMREC."),
    },
    "interesse_social": {
        "artigo": "Art. 147",
        "rotulo": "Empreendimento de Interesse Social",
        "texto": ("A implantação de Empreendimentos de Interesse Social "
                  "observará os parâmetros urbanos de ocupação específicos, "
                  "independente da Zona na qual esteja inserido, conforme "
                  "dispostos no Anexo III – Tabela de Parcelamento do Solo."),
        # A Tabela de Parcelamento do Solo (Tabela 2, p. 200) traz apenas
        # parâmetros de PARCELAMENTO. Não há nela ALML nem ATME.
        "atinge_alml": False,
        "altera": {"area_min_m2": 125.0, "testada_min_m": 5.0},
        "nao_altera": ["ALML (taxa de ocupação)", "ATME",
                       "altura máxima", "afastamentos"],
        "erro_de_remissao": (
            "O art. 147 remete ao 'Anexo III – Tabela 8 – Tabela de "
            "Parcelamento do Solo'. A Tabela 8 é a de Afastamentos; a Tabela "
            "de Parcelamento do Solo é a Tabela 2 (p. 200). Adotamos a "
            "Tabela 2, que é a que tem o nome citado — mas a remissão está "
            "errada no texto sancionado e convém confirmar com a SEMREC."),
        "observacao": (
            "A Tabela 2 fixa apenas área e testada mínimas do lote "
            "(125,00 m² e 5,00 m na coluna Residencial de Interesse Social). "
            "Ela NÃO traz ALML nem ATME: apesar de o art. 147 falar em "
            "'parâmetros urbanos de ocupação', a tabela para a qual ele "
            "remete é de parcelamento. Logo o Interesse Social não altera a "
            "ALML da zona."),
    },
}

# ---------------------------------------------------------------------------
# ANEXO III — TABELA 2: Parcelamento do Solo (p. 200)
#
# O porte do loteamento residencial define quanto se doa ao Municipio, e a
# escala e dupla — area OU numero de unidades, o que vier primeiro. As demais
# linhas da tabela nao se subdividem por porte: valem por USO.
# ---------------------------------------------------------------------------
PORTES_RESIDENCIAL = [
    # (rotulo, area_max_ha, unidades_max, verde_pct, institucional_pct)
    ("Ate 1 ha ou 35 unidades",       1.0,  35,   8.0, None),
    ("Ate 3 ha ou 60 unidades",       3.0,  60,   8.0, 3.0),
    ("Ate 5 ha ou 90 unidades",       5.0,  90,   8.0, 5.0),
    ("Acima de 5 ha ou 90 unidades",  None, None, 8.0, 8.0),
]

TABELA_2 = {
    "residencial": {
        "rotulo": "Loteamento residencial",
        "artigo_classe": "Art. 30, I",
        "portes": PORTES_RESIDENCIAL,
        "quadra_area_max_m2": 62500.0,
        "quadra_testada_max_m": 250.0,
        "lote_area_min_m2": 150.0,
        "lote_testada_min_m": 7.5,
    },
    "interesse_social": {
        "rotulo": "Loteamento residencial de interesse social",
        "artigo_classe": "Art. 30, II",
        "verde_pct": 5.0,
        "institucional_pct": 5.0,
        "quadra_area_max_m2": 62500.0,
        "quadra_testada_max_m": 250.0,
        "lote_area_min_m2": 125.0,
        "lote_testada_min_m": 5.0,
        "dispensa_dimensoes": ("Art. 35, IV — os parcelamentos destinados a "
                               "Empreendimentos Habitacionais de Interesse "
                               "Social nao estao sujeitos as dimensoes do "
                               "caput do art. 35."),
    },
    "industrial": {
        "rotulo": "Loteamento industrial",
        "artigo_classe": "Art. 30, III",
        "verde_pct": 5.0,
        "institucional_pct": 5.0,
        "quadra_area_max_m2": 90000.0,
        "quadra_testada_max_m": 300.0,
        "lote_area_min_m2": 1000.0,
        "lote_testada_min_m": 20.0,
        "ressalva": ("Art. 35, V — a localizacao de parcelamentos industriais "
                     "depende de parecer autorizativo da SEMMAM."),
    },
}

# ---------------------------------------------------------------------------
# ANEXO III — TABELA 3 e arts. 183/184: hierarquia viaria.
# A largura da Tabela 3 e de MEIO-FIO A MEIO-FIO (art. 183); a calcada vem
# somada dos dois lados (art. 184). A faixa total e o que consome a gleba.
# ---------------------------------------------------------------------------
TABELA_3 = [
    {"via": "estrutural", "rotulo": "Via Estrutural",
     "leito_m": 12.0, "calcada_m": 3.5, "artigo": "Art. 183, I / Art. 184, I"},
    {"via": "coletora", "rotulo": "Via Coletora",
     "leito_m": 10.0, "calcada_m": 2.5, "artigo": "Art. 183, II / Art. 184, II"},
    {"via": "local", "rotulo": "Via Local",
     "leito_m": 7.0, "calcada_m": 1.9, "artigo": "Art. 183, III / Art. 184, III"},
]
for _v in TABELA_3:
    _v["faixa_total_m"] = round(_v["leito_m"] + 2 * _v["calcada_m"], 2)

# ---------------------------------------------------------------------------
# Regras do parcelamento. "aferivel" separa o que o dado disponivel permite
# checar do que depende de levantamento em campo — e a diferenca entre um
# alerta util e um palpite com cara de laudo.
# ---------------------------------------------------------------------------
REGRAS_PARCELAMENTO = {
    "quadra_max": {
        "artigo": "Art. 39, I e II", "aferivel": True, "valor": 250.0,
        "texto": ("O comprimento das quadras nao podera ser superior a 250m e "
                  "a largura das quadras nao podera ultrapassar 250m."),
    },
    "quadra_vias_no_perimetro": {
        "artigo": "Art. 39, III", "aferivel": True,
        "texto": "As quadras devem possuir vias ao longo de todo o seu perimetro.",
    },
    "lote_esquina": {
        "artigo": "Art. 35, I", "aferivel": True, "valor": 10.0,
        "texto": ("Nos lotes de esquina de quadras, a menor testada devera "
                  "observar a dimensao minima de 10,00m, exceto para "
                  "Empreendimentos Habitacionais de Interesse Social."),
    },
    "gleba_inteira": {
        "artigo": "Art. 21", "aferivel": False,
        "texto": ("O parcelamento do solo de uma gleba so sera permitido "
                  "quando abranger a totalidade da gleba titulada."),
    },
    "zpa_fora_da_doacao": {
        "artigo": "Art. 21, I e II", "aferivel": True,
        "texto": ("Quando na gleba incidir ZPA ou APP, esta devera ser "
                  "excluida dos percentuais de doacao da Tabela 2. A area de "
                  "APP podera compor o percentual de area verde."),
    },
    "lote_nao_limita_com_zpa": {
        "artigo": "Art. 23", "aferivel": True,
        "texto": ("Nao sao permitidos lotes limitados por rios, riachos, ZPA, "
                  "Unidades de Conservacao e APPs — apenas areas publicas, "
                  "verdes, pracas, parques, circulacao, ciclovias e passeios "
                  "podem fazer limite com elas, garantindo o livre acesso."),
    },
    "zona_de_maior_insercao": {
        "artigo": "Art. 22", "aferivel": True,
        "texto": ("Na gleba que pertenca a duas ou mais Zonas, aplicam-se os "
                  "parametros da Zona na qual estiver inserida a maior "
                  "porcentagem da gleba."),
    },
    "integracao_viaria": {
        "artigo": "Art. 13", "aferivel": True,
        "texto": ("Todo parcelamento deve ser integrado a estrutura urbana "
                  "existente, mediante conexao do sistema viario e das redes "
                  "de servicos publicos."),
    },
    "declividade": {
        "artigo": "Art. 17, V e VI", "aferivel": False,
        "texto": ("Vedado o parcelamento em terrenos com declividade igual ou "
                  "superior a 30%, salvo exigencias da SEMOSP/SEMMAM, e em "
                  "declividade igual ou superior a 45 graus."),
    },
    "terreno_alagadico": {
        "artigo": "Art. 17, I a IV", "aferivel": False,
        "texto": ("Vedado em terrenos alagadicos ou sujeitos a inundacao, "
                  "aterrados com residuos, com condicoes geologicas "
                  "desaconselhaveis ou com poluicao."),
    },
    "verde_perimetro_unico": {
        "artigo": "Art. 36, V", "aferivel": True, "valor": 2500.0,
        "texto": ("A Area Verde deve estar contida em um so perimetro, "
                  "podendo ser dividida somente quando cada parcela resultante "
                  "possuir area minima de 2.500,00m2."),
    },
    "verde_nao_contigua_a_lotes": {
        "artigo": "Art. 36, III", "aferivel": False, "valor": 2500.0,
        "texto": ("A Area Verde nao deve ficar contigua a lotes, exceto quando "
                  "a area total a ser doada for inferior a 2.500,00m2, desde "
                  "que um dos lados faca frente para via publica."),
    },
    "institucional_testada": {
        "artigo": "Art. 38, II", "aferivel": True, "valor": 20.0,
        "texto": ("A Area Institucional deve ter testada igual ou superior a "
                  "20,00m e profundidade igual ou superior as determinadas "
                  "para os lotes."),
    },
    "institucional_divisao": {
        "artigo": "Art. 38, III e IV", "aferivel": True, "valor": 1000.0,
        "texto": ("A Area Institucional deve estar contida em um so perimetro, "
                  "divisivel apenas em parcelas de no minimo 1.000,00m2, e nao "
                  "mais de 3 areas quando a gleba for menor ou igual a 20ha."),
    },
    "unificacao_gleba_pequena": {
        "artigo": "Art. 40", "aferivel": True, "valor": 20000.0,
        "texto": ("Em glebas inferiores a 2ha a Prefeitura podera verificar a "
                  "necessidade de unificar as areas Verde e Institucional, "
                  "mantida a soma dos percentuais."),
    },
    "praca_de_reversao": {
        "artigo": "Art. 41, III", "aferivel": True, "valor": 12.0,
        "texto": ("As vias devem ligar duas outras vias; rua sem saida so e "
                  "aceita com praca de reversao que permita inscrever um "
                  "circulo de raio igual ou superior a 12,00m."),
    },
    "infraestrutura_basica": {
        "artigo": "Art. 19", "aferivel": False,
        "texto": ("Todo parcelamento deve ter infraestrutura basica: agua, "
                  "drenagem, iluminacao publica, energia domiciliar, "
                  "arborizacao, pavimentacao das vias e calcadas, "
                  "acessibilidade e esgotamento sanitario."),
    },
    "aprovacao_legislativa": {
        "artigo": "Art. 31", "aferivel": False,
        "texto": ("Apos parecer da SEMREC, o projeto de loteamento deve ser "
                  "submetido a aprovacao pelo poder legislativo municipal."),
    },
}

# Condominio NAO e loteamento: percentuais proprios (arts. 45 e 46) e vias
# privadas. Registrado para o app nao confundir os dois regimes.
CONDOMINIO = {
    "artigo": "Art. 44 a 48",
    "gleba_max_sem_carta_m2": 62500.0,
    "institucional_pct": {"area_parcelada": 0.0, "ate_62500": 8.0},
    "verde_pct": {"area_parcelada": 5.0, "ate_62500": 8.0},
    "mobiliario_max_pct": 10.0,
    "piso_drenante_max_pct": 30.0,
    "texto": ("Nos condominios as vias sao de dominio privado e os percentuais "
              "sao os dos arts. 45 e 46, nao os da Tabela 2. Glebas acima de "
              "62.500m2 dependem de Carta de Viabilidade Tecnica."),
}


# Art. 115 — empena cega. A ocupação da lateral, não a edificação, é que fica
# limitada a 9 m: um prédio alto pode encostar na divisa até essa cota e
# recuar acima dela.
EMPENA_CEGA = {
    "artigo": "Art. 115",
    "altura_max_m": 9.0,
    "texto": ("A edificação poderá ocupar um dos afastamentos laterais desde "
              "que não haja aberturas e/ou ventilação de qualquer natureza "
              "voltadas para os lotes vizinhos, desde que não ultrapasse "
              "9,00m (nove metros) de altura."),
    "condicoes": ["apenas UM dos afastamentos laterais",
                  "fachada sem aberturas nem ventilação para o vizinho",
                  "a ocupação vai até 9,00 m; acima disso o afastamento volta"],
    "ressalva": ("Nas zonas rurais o art. 113 proíbe edificar a menos de "
                 "3,00 m do terreno vizinho, o que afasta a empena cega."),
}

# ---------------------------------------------------------------------------
# ANEXO III — TABELA 6: Adequação dos usos às zonas (p. 264 a 266).
# A matriz subgrupo x classe NÃO é transcrita: são três tabelas grandes e um
# erro de coluna trocaria "adequado" por "inadequado" numa consulta de uso.
# Registramos os GRUPOS e as zonas que a lei nomeia em cada um — isso é
# verbatim e suficiente para dizer qual tabela consultar.
# ---------------------------------------------------------------------------
TABELA_6 = {
    "6.1": {"titulo": "Zonas Rurais",
            "zonas": ["ZRMS", "ZRI", "ZRBJJ", "ZRG"],
            "pagina": 264},
    "6.2": {"titulo": "Zonas de Preservação Ambiental",
            "zonas": ["ZPA SAO PAULO", "ZPA JENIPARANA"],
            "pagina": 265},
    "6.3": {"titulo": "Zonas Urbanas",
            "zonas": ["ZS", "ZEU", "ZDU - A", "ZDU - BV", "ZDU - P", "ZC"],
            "pagina": 266},
}

FAMILIA_PARA_TABELA6 = {"rural": "6.1", "ambiental": "6.2", "urbana": "6.3"}


def confere_pdfs():
    """Relê o autógrafo e confirma que a transcrição bate com a origem."""
    try:
        from pypdf import PdfReader
    except ImportError:
        print("  (pypdf ausente — pulei a conferência do PDF;")
        print("   instale com: pip install pypdf)")
        return None
    if not os.path.exists(PDF):
        print(f"  (não achei {PDF} — pulei a conferência)")
        return None
    r = PdfReader(PDF)
    txt = "\n".join((pg.extract_text() or "") for pg in r.pages[265:269])
    norm = re.sub(r"\s+", " ", txt)

    problemas = []
    for sigla, (nome, _t, amin, test, atme, alml, alt) in TABELA_7.items():
        amin_s = f"{amin:.2f}".replace(".", ",")
        test_s = (f"{test:.1f}".replace(".", ",") if test % 1 else f"{int(test)}")
        alvo = f"{amin_s} {test_s} {atme} {alml} {alt}"
        if alvo not in norm:
            problemas.append(f"Tabela 7 / {sigla}: não achei «{alvo}» no PDF")
    for gmin, gmax, fr, lat, fu in TABELA_8:
        if lat is None:                 # linha com '*': confere só o frontal
            faixa = f"{gmin} a {gmax} {fr:g} * *"
            if faixa not in norm:
                problemas.append(f"Tabela 8 / gabarito {gmin}-{gmax}: "
                                 f"não achei «{faixa}»")
            continue
        alvo = " ".join(f"{v:g}".replace(".", ",") for v in (fr, lat, fu))
        if alvo not in norm:
            problemas.append(f"Tabela 8 / gabarito {gmin}-{gmax}: "
                             f"não achei «{alvo}»")
    return problemas


def afastamentos_para(gabarito):
    """
    Afastamentos de um gabarito, aplicando o art. 111 onde a Tabela 8 grafa '*'.

    Retorna None acima de 30 pavimentos: a lei não define, e extrapolar aqui
    seria inventar parâmetro.
    """
    for gmin, gmax, fr, lat, fu in TABELA_8:
        if not gmin <= gabarito <= gmax:
            continue
        faixa = f"{gmin}" if gmin == gmax else f"{gmin} a {gmax}"
        if lat is not None:
            return {"frontal_m": fr, "lateral_m": lat, "fundos_m": fu,
                    "faixa": faixa, "fonte": "Anexo III, Tabela 8"}
        for amin, amax, inc, inciso in ACRESCIMO_ART111:
            if amin <= gabarito <= amax:
                v = round(BASE_LATERAL_ART111 + (gabarito - 5) * inc, 2)
                return {"frontal_m": fr, "lateral_m": v, "fundos_m": v,
                        "faixa": faixa,
                        "fonte": f"Tabela 8 (frontal) + art. 111, {inciso}",
                        "calculo": (f"{BASE_LATERAL_ART111:g} m + "
                                    f"({gabarito} - 5) x {inc:g} m"),
                        "acrescimo_m_por_pav": inc}
    return None


def main():
    print("LEIS (Lei Complementar nº 77/2025 — autógrafo)")

    problemas = confere_pdfs()
    if problemas is None:
        pass
    elif problemas:
        print(f"  ATENÇÃO: {len(problemas)} divergência(s) entre a transcrição "
              f"e o PDF:")
        for p in problemas:
            print(f"    - {p}")
        print("  Revise TABELA_7/TABELA_8 neste arquivo antes de confiar na saída.")
    else:
        print(f"  transcrição conferida contra o PDF: "
              f"{len(TABELA_7)} zonas e {len(TABELA_8)} faixas de afastamento OK")

    zonas = {}
    for sigla, (nome, tipo, amin, test, atme, alml, alt) in TABELA_7.items():
        zonas[sigla] = {
            "sigla": sigla, "nome": nome, "tipo": tipo,
            "area_min_m2": amin,
            "testada_min_m": test,
            "atme_pct": atme,
            "coef_aproveitamento": round(atme / 100, 2),
            "alml_pct": alml,
            "taxa_ocupacao_max_pct": 100 - alml,
            "altura_max_m": alt,
            "fonte": "Anexo III, Tabela 7 (autógrafo p. 267)",
        }

    # ---- cobertura: geometria da lei x parâmetros da lei ----
    zpath = os.path.join(PROC, "zoneamento.geojson")
    geo_siglas, tab6, com_geo, sem_param = [], {}, [], []
    if os.path.exists(zpath):
        with open(zpath, encoding="utf-8") as f:
            geo = json.load(f)
        for feat in geo["features"]:
            p = feat["properties"]
            s = p["sigla"]
            geo_siglas.append(s)
            tab6[s] = FAMILIA_PARA_TABELA6.get(p.get("familia"))
            (com_geo if s in zonas else sem_param).append(s)
    else:
        print("  (zoneamento.geojson ausente — rode 09_zonas_lei.py)")

    sem_geo = [s for s in zonas if s not in geo_siglas]

    tabela_afast = []
    for gmin, gmax, *_ in TABELA_8:
        a = afastamentos_para(gmin)
        b = afastamentos_para(gmax)
        tabela_afast.append({
            "gabarito_min": gmin, "gabarito_max": gmax,
            "frontal_m": a["frontal_m"],
            "lateral_m_min": a["lateral_m"], "lateral_m_max": b["lateral_m"],
            "fundos_m_min": a["fundos_m"], "fundos_m_max": b["fundos_m"],
            "tabelado": gmax <= 5,
            "fonte": a["fonte"],
        })

    saida = {
        "lei": LEI,
        "zonas": zonas,
        "zonas_sem_parametro": SEM_PARAMETRO,
        "afastamentos_por_gabarito": tabela_afast,
        "afastamentos_por_pavimento": {
            str(n): afastamentos_para(n) for n in range(1, 31)},
        "afastamentos_fonte": ("Anexo III, Tabela 8 (autógrafo p. 268) e "
                               "art. 111, incisos II a IV"),
        "afastamentos_ressalvas": RESSALVAS_TABELA_8,
        "gabarito_max_parametrizado": 30,
        "regras": REGRAS,
        "exclusoes_atme": EXCLUSOES_ATME,
        "instrumentos_ausentes": INSTRUMENTOS_AUSENTES,
        "empena_cega": EMPENA_CEGA,
        "alteracao_indices": ALTERACAO_INDICES,
        "parcelamento": {"tabela_2": TABELA_2, "vias": TABELA_3,
                         "regras": REGRAS_PARCELAMENTO,
                         "condominio": CONDOMINIO},

        "atme_varia_com_gabarito": False,
        "usos": {"tabelas": TABELA_6, "por_zona": tab6,
                 "fonte": "Anexo III, Tabela 6 (autógrafo p. 264 a 266)"},
        "cobertura": {
            "zonas_com_geometria_e_parametro": sorted(com_geo),
            "zonas_com_geometria_sem_parametro": sorted(sem_param),
            "zonas_com_parametro_sem_geometria": sorted(sem_geo),
        },
    }
    write_json(os.path.join(PROC, "lei.json"), saida)

    # ---- relatório ----
    print(f"\n  Zonas com parâmetro (Tabela 7)        : {len(zonas)}")
    print(f"  Zonas com geometria (memoriais)       : {len(geo_siglas)}")
    print(f"  Com geometria E parâmetro             : {len(com_geo)}")
    for s in sorted(com_geo):
        z = zonas[s]
        print(f"    {s:<9} ATME {z['atme_pct']:>3}% | ocupação máx "
              f"{z['taxa_ocupacao_max_pct']:>2}% | altura {z['altura_max_m']:>2} m "
              f"| lote ≥ {z['area_min_m2']:.0f} m², testada ≥ "
              f"{z['testada_min_m']:g} m")
    if sem_param:
        print(f"\n  Com geometria, SEM linha na Tabela 7 ({len(sem_param)}):")
        for s in sorted(sem_param):
            print(f"    {s:<18} {SEM_PARAMETRO.get(s, '(?)')}")
        print("    A lei não fixa ATME/ALML/altura para estas zonas.")
        print("    O app as marca como indeterminadas, não como liberadas.")
    if sem_geo:
        print(f"\n  Com parâmetro, SEM geometria ({len(sem_geo)}): "
              f"{', '.join(sorted(sem_geo))}")
    else:
        print("\n  Toda zona da Tabela 7 tem memorial descritivo. OK")

    print("\n  Afastamentos (Tabela 8 + art. 111):")
    for n in (1, 2, 5, 6, 10, 11, 20, 21, 30):
        a = afastamentos_para(n)
        calc = f"   [{a['calculo']}]" if "calculo" in a else ""
        print(f"    {n:>2} pav  frontal {a['frontal_m']:>5.2f}  "
              f"lateral {a['lateral_m']:>5.2f}  fundos {a['fundos_m']:>5.2f}"
              f"{calc}")
    print(f"    31+ pav  {afastamentos_para(31)}  (a lei não define)")

    mod = [e for e in EXCLUSOES_ATME if e["modelavel"]]
    print(f"\n  Area construida PODE superar a ATME (arts. 100 a 105):")
    for e in EXCLUSOES_ATME:
        marca = "modelavel" if e["modelavel"] else "informativo"
        print(f"    {e['artigo']:<9} {e['chave']:<11} [{marca}]"
              + (f"  {'; '.join(e['condicoes'])}" if e["condicoes"] else ""))
    print(f"    -> {len(mod)} exclusoes viram pavimento no bloco 3D; "
          f"{len(EXCLUSOES_ATME)-len(mod)} ficam so no texto.")
    print("\n  A ATME NAO varia com o gabarito: e percentual fixo da area do")
    print("  lote, igual para 2 ou para 20 pavimentos.")
    print("  Sem solo criado, sem outorga onerosa, sem transferencia de")
    print("  potencial — zero ocorrencias no autografo.")

    print("\n  Hipoteses em que a lei admite afastar-se da Tabela 7:")
    for k, v in ALTERACAO_INDICES.items():
        alc = "DISPENSA a ALML" if v["atinge_alml"] else "NAO altera a ALML"
        print(f"    {v['artigo']:<9} {v['rotulo']:<42} {alc}")
        for c in v.get("condicoes", []):
            print(f"              - {c}")
        if "altera" in v:
            print(f"              - altera: {v['altera']}")
    print("    -> Fora dessas hipoteses, ALML e ATME sao fixos por zona.")


if __name__ == "__main__":
    main()

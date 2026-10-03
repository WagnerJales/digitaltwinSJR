# SJR-Geo — Gêmeo Digital Urbano de São José de Ribamar - MA

Protótipo inspirado na plataforma OSPA place (Itajaí 360º), sobre stack 100%
aberta. Roda sobre os **dados reais** do município: a Lei Complementar
77/2025, o Censo 2022, as edificações do Open Buildings e a malha viária do
OpenStreetMap.

> **Sem valor legal.** Não substitui a Certidão de Uso e Ocupação do Solo nem
> qualquer ato da Prefeitura. Confira sempre a redação vigente da lei.

---

## Abrir

**Duplo clique em `dist/SJR-Geo.html`.** É o aplicativo com todos os dados
embutidos (10,5 MB) — funciona sem servidor e sem internet, exceto pelo mapa
de fundo e pela biblioteca MapLibre.

Para a versão servida, que reflete o pipeline sem precisar regerar nada:

```bash
ABRIR.bat                      # Windows — sobe o servidor e abre o navegador
./abrir.sh                     # Linux/macOS
# ou, à mão:
python -m http.server 8080     # depois abra http://localhost:8080/web/
```

> `web/index.html` **não funciona por duplo clique**: ele lê os dados por
> `fetch`, e o navegador bloqueia `fetch` em `file://`. O aplicativo detecta
> isso e explica na tela.

## Reprocessar

```bash
python pipeline/run_all.py                # ~110 s, reconstrói tudo
python pipeline/run_all.py --completo      # + edificações do município inteiro
```

**Sem dependências** — apenas a stdlib do Python 3, com uma exceção: o
`pypdf`, usado para ler a lei (`pip install pypdf`). Nada de geopandas,
shapely ou fiona, o que também resolve a falta de wheels dessas bibliotecas
para o Python 3.14.

## Testar

```bash
node tests/test_geometria.js      # motor de cálculo: geometria e lei
node tests/test_app.js            # partida do app: camadas e fontes
node tests/test_carregamento.js   # falhas de rede e configuração dos basemaps
python pipeline/qa_dados.py       # auditoria dos dados
```

---

## Estrutura

```
SIG/                  entradas brutas (854 MB, não versionado)
leis/                 PDFs da legislação
pipeline/             processamento — 13 scripts Python
data/processados/     saídas do pipeline (não versionado)
web/index.html        O APLICATIVO — código-fonte, 3.700 linhas
tests/                testes (Node, sem dependências)
dist/SJR-Geo.html     entregável gerado (não versionado)
ABRIR.bat, abrir.sh   sobem o servidor local
```

**`web/index.html` é a fonte; `dist/SJR-Geo.html` é gerado a partir dele.**
Removendo o bloco `window.__EMBED` do arquivo gerado, o que sobra é byte a
byte idêntico ao `index.html`. Toda edição vai no `index.html`; o `dist/`
pode ser apagado e reconstruído com `python pipeline/gerar_standalone.py`.

---

## As fontes de dados

| Fonte | Arquivo | Volume | O que entrega |
|---|---|---|---|
| **LC 77/2025** (autógrafo) | `leis/LC_77_AUTOGRAFO.pdf` | 271 p. | zoneamento (memoriais) + todos os parâmetros |
| **Censo 2022** (IBGE) | `SIG/censo2022/` | 609 setores | população, domicílios, densidade |
| **Google Open Buildings v3** | `07f_buildings.csv` | 2,08 M linhas → 110.686 no município | footprints de edificação |
| **CNEFE 2022** (IBGE) | `2111201.csv` | 118.456 endereços | endereços por espécie |
| **OpenStreetMap** | `RIBAMAR.shp` | 5.592 → 5.303 vias | malha viária com hierarquia |

### Duas armadilhas nos nomes dos arquivos

1. **`RIBAMAR_LOTES.shp` não são lotes.** É o CNEFE — pontos de endereço,
   geometria `Point`. É byte a byte idêntico a
   `DOMICILIOS_SAO_JOSE_DE_RIBAMAR.shp` e ao `2111201.csv`. Os três são o
   mesmo dado.
2. **`RIBAMAR.shp` são vias, não o limite municipal.** É uma extração OSM.

### O KMZ foi descartado

O `ZONEAMENTO_RIBAMAR.kmz` trazia 44 zonas (ZR 1..ZR 10, ZDS 1..3, ZITC,
ZIPA…) cujas siglas **não constam da lei**, e divergia dela na altura por
fatores de 2,5× a 5×. Era outra versão do zoneamento. O zoneamento hoje vem
dos **memoriais descritivos da própria lei**, o que elimina a divergência na
origem: geometria e parâmetros saem do mesmo documento.

---

## O zoneamento vem da lei, vértice a vértice

[`pipeline/09_zonas_lei.py`](pipeline/09_zonas_lei.py) lê os 13 memoriais
descritivos do Anexo III — Tabela 1 do autógrafo, converte as coordenadas de
**UTM 23S / SIRGAS 2000 para WGS84** (inversa exata da Transversa de
Mercator, Snyder / USGS PP 1395) e monta os polígonos.

**3.417 vértices** extraídos. As verificações que o pipeline faz a cada
execução:

| Verificação | Resultado |
|---|---|
| Índices `Pt0..PtN` contíguos e sem duplicata | todos os 13 memoriais |
| Área por shoelace em UTM × área em WGS84 | divergência máxima **0,0578%** |
| Vértices dentro do município | 3.417 de 3.417 |
| Anéis fechados, sem auto-interseção, orientação CCW | 13 de 13 |
| Toda zona da Tabela 7 tem memorial | sim |

A extração por índice `Pt` não é preciosismo: o extrator de texto do PDF
quebra algumas linhas ao meio, e a leitura linha a linha perdia vértices em
silêncio (Pt257 da ZRMS, Pt144 e Pt147 da ZPA Jeniparana). A ZDU-P tem 16
vértices consecutivos com coordenada idêntica — lados de comprimento zero no
próprio texto da lei.

### Cobertura do território

| | km² |
|---|---|
| Área territorial do município (IBGE, 2022) | **180,363** |
| Soma dos 609 setores censitários | 180,36 |
| Soma das 13 zonas da lei | **178,92** → 99,2% |

Os memoriais cobrem praticamente todo o município.

---

## O que a Lei Complementar 77/2025 define

[`pipeline/16_leis.py`](pipeline/16_leis.py) transcreve as tabelas e **relê o
PDF a cada execução para conferir a transcrição** — se a fonte mudar, ele
avisa em vez de seguir com número velho.

### Anexo III, Tabela 7 — parâmetros por zona (p. 267)

- **ATME** — Área Total Máxima de Edificação: razão máxima entre área
  construída e área do terreno. É o coeficiente de aproveitamento, em %.
- **ALML** — Área Livre Mínima do Lote. Taxa de ocupação máxima = 100 − ALML.

| Zona | Área mín. | Testada mín. | ATME | Ocupação máx. | Altura máx. |
|---|---|---|---|---|---|
| ZS — Sede | 150 m² | 7,5 m | 240 % | 70 % | 30 m |
| ZC — Central | 150 m² | 7,5 m | 240 % | 70 % | 15 m |
| ZEU — Expansão Urbana | 150 m² | 7,5 m | 360 % | 70 % | 60 m |
| ZDU-A / BV / P | 150 m² | 7,5 m | 370 % | 60 % | 90 m |
| ZRMS — Mata/Santana | 200 m² | 10 m | 360 % | 70 % | 60 m |
| ZRI / ZRBJJ / ZRG | 200 m² | 10 m | 180 % | 60 % | 60 m |

São **10 zonas com parâmetro**. As três ambientais — **ZPA São Paulo**, **ZPA
Jeniparana** e **Parque da Quinta** — têm memorial descritivo mas **nenhuma
linha na Tabela 7**. Nelas o app marca ATME, ALML e altura como
*indeterminados*, que não é o mesmo que *liberados*.

> **Não existe ZAAJ.** Zero ocorrências no autógrafo. Versões anteriores deste
> README traziam uma tabela com ATME errado em todas as linhas, transcrita do
> `BOOK_PLZoneamenyo_SJR.pdf`, que é o **projeto** de lei, não o texto
> sancionado.

### Anexo III, Tabela 8 c/c art. 111 — afastamentos por gabarito

Os afastamentos dependem do **gabarito**, não da zona.

| Gabarito | Frontal | Lateral | Fundos | Origem |
|---|---|---|---|---|
| 1 (térreo) | 5 m | 1,5 m | 1,5 m | tabelado |
| 2 | 5 m | 2 m | 1,5 m | tabelado |
| 3 a 5 | 5 m | 3 m | 3 m | tabelado |
| 6 a 10 | 6 m | 3,65 a 6,25 m | 3,65 a 6,25 m | art. 111, II |
| 11 a 20 | 8 m | 6,30 a 11,25 m | 6,30 a 11,25 m | art. 111, III |
| 21 a 30 | 10 m | 10,20 a 14,25 m | 10,20 a 14,25 m | art. 111, IV |

Acima do 5º pavimento a tabela grafa `*` em lateral e fundos e remete ao
art. 111, que manda acrescer 0,65 / 0,55 / 0,45 m **por pavimento contado a
partir do quinto**. Não é valor de faixa: muda pavimento a pavimento.

Três ressalvas, registradas no app e não decididas por conta própria:

- **Base do acréscimo**: adotamos 3,00 m, o último valor tabelado. O frontal
  é lido direto da tabela, sem acréscimo, porque a nota `*` só marca lateral
  e fundos.
- **Descontinuidade no 21º pavimento**: o lateral cai de 11,25 m para 10,20 m,
  porque o incremento diminui. Aplicado como escrito.
- **Acima de 30 pavimentos** a lei não define afastamento. O gabarito para
  ali por falta de parâmetro, não por vedação.

### Regras gerais, com o artigo citado no app

Permeabilidade de **20% em todas as zonas** (Art. 98); 50% da ALML deve ser
100% permeável (Art. 106); pé-direito mínimo 2,60 m (Art. 109); número de
pavimentos livre, limitado pela altura (Art. 114); **um afastamento frontal
por testada** (Art. 112); altura medida pela maior testada (Art. 107, I);
elevador acima de 5 pavimentos (Art. 110); subsolo (Art. 118).

### Quando a área construída pode superar a ATME

A ATME **não varia com o gabarito** — é percentual fixo da área do lote,
igual para 2 ou 20 pavimentos. O que a lei faz é retirar da conta certas
áreas, em função do **uso** do pavimento:

| Art. | Não computa na ATME | Modelado no 3D |
|---|---|---|
| 100 | Unidades na cobertura, até 50% da laje | sim |
| 101 | Pavimentos de uso exclusivo de garagem | sim |
| 105 | Pilotis (não computa na ATME, mas **computa na altura**) | sim |
| 102 | Circulação vertical e horizontal | informativo |
| 103 | Áreas de uso comum | informativo |
| 104 | Pergolados, beirais, shafts, dutos | informativo |

Os arts. 102 a 104 são frações internas de cada laje; arbitrar um percentual
inflaria a área sem respaldo em projeto. Na prática, **a área construída real
tende a ser maior que a calculada aqui**.

### Quando a ALML pode ser dispensada

Busca no texto integral: **duas hipóteses, e só uma alcança a ALML.**

- **Art. 117 — reforma em lote de Regularização Fundiária.** Dispensa os
  índices urbanísticos, exceto taxa de permeabilidade e altura máxima. Vale
  só para *reforma*.
- **Art. 147 — Empreendimento de Interesse Social.** Remete à Tabela de
  Parcelamento do Solo, que traz apenas área mínima de 125 m² e testada de
  5,00 m. **Não altera a ALML nem a ATME.** O artigo cita "Tabela 8", mas a
  Tabela 8 é a de Afastamentos — a de Parcelamento é a Tabela 2. Erro de
  remissão no texto sancionado.

Ambas entram no app como *Regime do lote*, com as condições de fato que o
usuário declara. **Não há solo criado, outorga onerosa nem transferência do
direito de construir** na LC 77/2025 — zero ocorrências.

---

## Funcionalidades

Consulta de zona com seleção múltipla, **estudo de viabilidade sobre lote
desenhado**, bloco 3D da possibilidade construtiva, densidade do Censo por
setor, edificações em 3D, mapa de calor de endereços, malha viária por
hierarquia, painel de indicadores, 2D/3D, basemap claro/satélite, medição de
distância, busca de endereço, **permalink**, export em GeoJSON e laudo em PDF.

### Estudo de viabilidade

A OSPA place faz o estudo clicando num lote do cadastro. Como São José de
Ribamar **não tem cadastro imobiliário georreferenciado**, aqui o usuário
desenha o terreno e o cálculo roda sobre o polígono dele, no navegador.

O afastamento frontal é medido **perpendicularmente ao eixo da via**, não à
aresta desenhada — é o eixo que define o alinhamento predial. Para cada
aresta, o app busca o segmento viário mais próximo e mede distância e ângulo;
é testada quando está a ≤ 15 m com desalinhamento ≤ 35°. Lote de esquina
recebe afastamento em **todas** as testadas (Art. 112).

### A regra que governa o cálculo

| | O que limita | Efeito |
|---|---|---|
| **Altura máxima** | Tabela 7, em metros | limita **pavimentos** |
| **ATME** | % da área do lote | limita **área**, não pavimentos |
| **ALML** | ocupação = 100 − ALML | limita a **projeção** de cada pavimento |
| **Afastamentos** | Tabela 8 + art. 111 | reduzem a projeção |

O **Art. 114** é explícito: *"o número de pavimentos é livre desde que não
ultrapasse a altura máxima permitida pela zona"*. Atingir a ATME **não**
impede subir — obriga a construir menos por pavimento. O app separa
**bloqueios** (altura; afastamentos que consomem o lote) de **limites de
área** (ATME, ocupação) e nunca usa os segundos para travar o gabarito.

**Subir até o teto legal costuma não ser o melhor aproveitamento.** Pelo
art. 111 a laje encolhe mais rápido do que os pavimentos se somam: um lote de
14 × 40 m na ZEU chega a 12 pavimentos com 1.333 m², mas rende 1.637 m² com
8. O painel mostra os dois números.

### Alívios previstos na lei

- **Pódio (Art. 111, § 2º)** — ligado por padrão. Acima de 15 m, os cinco
  primeiros pavimentos usam os afastamentos de edificações de até 15 m.
- **Empena cega (Art. 115)** — a edificação ocupa **um** afastamento lateral,
  sem aberturas voltadas ao vizinho. O limite de 9,00 m é da **ocupação**,
  não do prédio: um prédio alto encosta na divisa até essa cota e recua acima
  dela. O usuário escolhe a divisa; ela sai destacada no mapa.
- **Art. 116** (redução de 50% da lateral em até 1/3 da profundidade) é apenas
  informado: é recorte parcial, dependente do projeto.

### O invariante que sustenta tudo

**Os números declarados são calculados a partir da geometria final, nunca o
contrário.** Cada pavimento é recortado pelo de baixo — uma laje precisa de
apoio — e os totais saem da medição dos anéis desenhados.

Isso não é obviedade: quatro defeitos seguidos tiveram a mesma forma — um
limite legal aplicado ao *número* e não à *geometria*. O painel dizia
8.177 m² (a ATME) e o bloco desenhado somava 16.342 m². A seção **11e** do
`test_geometria.js` mede os anéis em 380 cenários e exige que fechem com o
declarado; maior desvio: **0,0004 m²**.

---

## Indicadores observados

O Censo dá o que a zona **tem**; a Tabela 7 dá o que ela **permite**. A
distância entre os dois é o que interessa a quem planeja.

| Zona | Setores | População | km² | hab./ha |
|---|---|---|---|---|
| ZC | 19 | 4.965 | 0,83 | **59,85** |
| ZS | 37 | 17.113 | 3,48 | 49,25 |
| ZEU | 393 | 165.463 | 47,90 | 34,54 |
| ZDU-A | 82 | 29.217 | 13,45 | 21,73 |
| **ZPA Jeniparana** | 39 | **15.031** | 17,92 | 8,39 |
| ZRMS | 9 | 3.677 | 8,69 | 4,23 |
| ZPA São Paulo | 1 | 237 | 0,89 | 2,67 |
| ZRI | 5 | 1.144 | 5,56 | 2,06 |
| ZDU-P | 15 | 3.865 | 21,72 | 1,78 |
| ZRBJJ | 6 | 3.418 | 46,78 | 0,73 |
| ZDU-BV | 2 | 449 | 6,22 | 0,72 |
| ZRG | 1 | 0 | 6,93 | 0,00 |

**Totais**: 244.579 habitantes, 102.279 domicílios particulares — dos quais
81.090 ocupados, 14.926 vagos (14,6%) e 6.263 de uso ocasional (6,1%).
110.686 edificações detectadas e 117.928 endereços do CNEFE.

Conferido contra a API do IBGE: população e área batem exatamente
(244.579 habitantes e 180,363 km²).

---

## Achados que a Prefeitura precisa resolver

1. **Não existe cadastro imobiliário georreferenciado.** É o gargalo: sem ele
   não há consulta por lote, só por zona. `15_lotes.py` já está escrito para
   o dia em que a base chegar.
2. **15.031 pessoas moram na ZPA Jeniparana**, em 39 setores — uma zona de
   proteção ambiental sem parâmetro de ocupação na Tabela 7.
3. **Art. 147 tem erro de remissão**: cita "Tabela 8 – Tabela de Parcelamento
   do Solo", mas a Tabela 8 é a de Afastamentos.
4. **A base do acréscimo do art. 111** não está escrita na lei. Adotamos
   3,00 m (o último valor tabelado); convém confirmar.
5. **A descontinuidade do 21º pavimento** provavelmente não é intencional.
6. **A Tabela 7 do autógrafo diverge do projeto de lei** em ATME, ALML e
   altura para todas as zonas. Vale confirmar qual texto está em vigor.

---

## Limitações conhecidas

- **O Open Buildings não fornece altura.** No 3D toda edificação aparece com
  um pavimento nominal. Altura real exigiria LiDAR ou o cadastro municipal.
- **A camada de edificações carrega só o núcleo urbano** — 18.544 de 110.686.
  O município inteiro em GeoJSON travaria o navegador. O tracejado no mapa
  marca onde os dados terminam; os números do painel são do município todo.
  Para o território completo: `run_all.py --completo` + PMTiles.
- Endereços e setores censitários **cobrem o município inteiro**.
- O cálculo não verifica adequação de uso (Tabela 6), vagas, acessibilidade
  nem relevo, e não aplica as exclusões dos arts. 102 a 104.
- O CNEFE conta *endereços*, não domicílios ocupados.
- Áreas por projeção equirretangular local (erro < 0,1% nesta escala).
- **Nenhuma chave de API no projeto.** Os basemaps da Esri e o Nominatim são
  usados em termos anônimos e têm políticas para volume alto; em produção
  municipal, planejar basemap próprio. A CARTO servia o mapa claro até passar
  a exigir chave — e recusava com um tile HTTP 200 escrito "api key
  required", que nenhuma detecção de status pega.
- **A biblioteca MapLibre vem de CDN (unpkg).** É a última dependência
  externa eliminável: vendorizar ~840 KB tornaria o `dist/SJR-Geo.html`
  realmente autônomo.

---

## Sobre `pipeline/_obsoleto/`

Scripts da fase em que o projeto rodava sobre dados fictícios, mais o
`10_zoneamento.py` que lia o KMZ. Arquivados porque **escreviam nos mesmos
caminhos de saída do pipeline real** — rodar qualquer um sobrescreveria os
dados verdadeiros. Ficam como referência histórica até o projeto entrar em
controle de versão.

## Aviso legal

Protótipo informativo, sem valor legal. Não substitui a Certidão de Uso e
Ocupação do Solo nem qualquer ato da Prefeitura Municipal de São José de
Ribamar. Confira sempre a redação vigente da Lei de Zoneamento e do Plano
Diretor (Lei Complementar nº 57/2020).

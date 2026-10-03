/* =====================================================================
   Testes do estudo de viabilidade de LOTEAMENTO.

       node tests/test_loteamento.js

   O outro estudo responde "que prédio cabe neste lote". Este responde a
   pergunta anterior: "quantos lotes saem desta gleba, e quanto dela vira
   rua, praça e área institucional".

   O que se verifica aqui não é o traçado — a lei não dita geometria — e sim
   que o traçado gerado RESPEITA os limites que a lei fixa: tamanho máximo de
   quadra (Art. 39), lote e testada mínimos (Tabela 2), percentuais de doação
   (Tabela 2), largura de via (Tabela 3), testada de esquina (Art. 35, I) e a
   exclusão da ZPA da base de doação (Art. 21, I).

   E que a soma das partes fecha com o todo — o mesmo invariante que já pegou
   quatro defeitos no estudo de edificação: geometria e números têm de contar
   a mesma história.
   ===================================================================== */
const fs = require('fs');
const path = require('path');

const RAIZ = path.join(__dirname, '..');
const PROC = path.join(RAIZ, 'data', 'processados');
const html = fs.readFileSync(path.join(RAIZ, 'web', 'index.html'), 'utf8');

let falhas = 0;
function afirma(ok, msg) {
  console.log((ok ? '  ok   ' : ' FALHA ') + msg);
  if (!ok) falhas++;
}
function perto(a, b, tol, msg) {
  const ok = Math.abs(a - b) <= tol;
  console.log((ok ? '  ok   ' : ' FALHA ') + msg
    + (ok ? '' : `: ${Number(a).toFixed(2)} (esperado ${Number(b).toFixed(2)} ±${tol})`));
  if (!ok) falhas++;
}
function fatia(ini, fim) {
  const a = html.indexOf(ini);
  // dizer QUAL marcador falhou: culpar o inicio quando o fim e que sumiu ja
  // custou tempo uma vez
  if (a < 0) {
    console.error(`ERRO: nao achei o INICIO "${ini.slice(0, 45)}".`);
    process.exit(1);
  }
  const b = html.indexOf(fim, a);
  if (b < 0) {
    console.error(`ERRO: nao achei o FIM "${fim.slice(0, 45)}" apos o inicio.`);
    process.exit(1);
  }
  return html.slice(a, b);
}
const proc = (n) => JSON.parse(fs.readFileSync(path.join(PROC, n), 'utf8'));

// blocos: geometria + analise do lote (traz frentesDoLote, zonaEm...) + motor
const geom = fatia('const M_LAT = 110574.0;', "map.on('load'");
const analise = fatia('let loteRing = [];',
  '   ESTUDO DE VIABILIDADE DE LOTEAMENTO');
const motor = fatia('let glebaRing = [];', '/** Desenha a gleba');

const G = new Function(`
  const PE_DIREITO_M = 3.0;
  let ZONAS_FC = null, VIAS_FC = null, PARAMS = {}, LEI = null;
  const fmt = (n,d=0) => Number(n).toFixed(d);
  const areaTxt = m => Number(m).toFixed(1) + ' m2';
  ${geom}
  ${analise}
  ${motor}
  return { analisaGleba, ehConvexo, porteResidencial, faixaVia, tabela2,
           geraQuadras, divideQuadra, shoelace, fecha, proj, areaAnelM2,
           opc: () => opcLote,
           opta: o => { Object.assign(opcLote, o); },
           reset: () => { Object.assign(opcLote, {uso:'residencial',
             via:'local', quadraComprimento_m:100, loteProfundidade_m:25,
             loteTestada_m:null}); },
           set: (z, v, p, l) => { ZONAS_FC = z; VIAS_FC = v; PARAMS = p;
             LEI = l;
             // zera os caches: indice de vias e bbox de zona do cenario
             // anterior contaminariam o proximo
             _zbox = null; _viaGrid = null; } };
`)();

// ---------------------------------------------------------------- cenario
const lei = proc('lei.json');
const O = [-44.12, -2.53];                       // dentro da ZEU
const KX = 111320 * Math.cos(O[1] * Math.PI / 180), KY = 110574;
const P2 = ([x, y]) => [O[0] + x / KX, O[1] + y / KY];
const quad = [[-2000,-2000],[2000,-2000],[2000,2000],[-2000,2000],[-2000,-2000]]
  .map(P2);
const VIAS = {type:'FeatureCollection', features:[{type:'Feature',
  properties:{nome:'Estrada Velha', tipo_osm:'residential'},
  geometry:{type:'LineString', coordinates:[[-1500,-8],[1500,-8]].map(P2)}}]};
const ZONA = {type:'FeatureCollection', features:[{type:'Feature',
  properties:{sigla:'ZEU'}, geometry:{type:'Polygon', coordinates:[quad]}}]};
G.set(ZONA, VIAS, {ZEU:{sigla:'ZEU', familia:'urbana'}}, lei);

const areaM = (anel) => Math.abs(G.shoelace(
  anel.map((p) => [(p[0] - O[0]) * KX, (p[1] - O[1]) * KY])));
const gleba = (w, h) => [[0,0],[w,0],[w,h],[0,h]].map(P2);

(async () => {
  console.log('\n1. a Tabela 2 chega ao motor');
  {
    const t = G.tabela2('residencial');
    afirma(!!t, 'uso residencial existe na Tabela 2');
    perto(t.lote_area_min_m2, 150, 0, 'lote minimo residencial = 150 m2');
    perto(t.lote_testada_min_m, 7.5, 0, 'testada minima = 7,50 m');
    perto(t.quadra_testada_max_m, 250, 0, 'quadra maxima = 250 m (Art. 39)');
    const his = G.tabela2('interesse_social');
    perto(his.lote_area_min_m2, 125, 0, 'Interesse Social: lote de 125 m2');
    perto(his.lote_testada_min_m, 5, 0, 'Interesse Social: testada de 5,00 m');
    const ind = G.tabela2('industrial');
    perto(ind.lote_area_min_m2, 1000, 0, 'Industrial: lote de 1.000 m2');
    perto(ind.quadra_area_max_m2, 90000, 0, 'Industrial: quadra de 90.000 m2');

    // Tabela 3: a largura da lei e de meio-fio a meio-fio; calcada soma
    const local = G.faixaVia('local');
    perto(local.leito_m, 7, 0, 'via local: leito de 7,00 m (Art. 183, III)');
    perto(local.calcada_m, 1.9, 0, 'calcada de 1,90 m (Art. 184, III)');
    perto(local.faixa_total_m, 10.8, 0.01,
      'faixa total = 7,00 + 2 x 1,90 = 10,80 m');
  }

  console.log('\n2. porte da Tabela 2 escala por area OU unidades');
  {
    const p1 = G.porteResidencial(9000, null);      // 0,9 ha
    afirma(p1.institucional_pct === null,
      'ate 1 ha: institucional "NA", sem percentual exigido');
    perto(p1.verde_pct, 8, 0, 'ate 1 ha: 8% de area verde');
    const p2 = G.porteResidencial(25000, null);     // 2,5 ha
    perto(p2.institucional_pct, 3, 0, 'ate 3 ha: 3% institucional');
    const p3 = G.porteResidencial(45000, null);     // 4,5 ha
    perto(p3.institucional_pct, 5, 0, 'ate 5 ha: 5% institucional');
    const p4 = G.porteResidencial(80000, null);     // 8 ha
    perto(p4.institucional_pct, 8, 0, 'acima de 5 ha: 8% institucional');
    // a escala e dupla: area pequena mas muitas unidades sobe o porte
    const pu = G.porteResidencial(9000, 200);
    perto(pu.institucional_pct, 8, 0,
      'REGRESSAO: 0,9 ha com 200 unidades cai no porte de 8%, nao no "NA"');
  }

  console.log('\n3. gleba de 200 x 150 m na ZEU');
  {
    G.reset();
    const g = gleba(200, 150);
    const r = G.analisaGleba(g);
    afirma(!!r, 'a gleba foi analisada');
    perto(r.area_m2, 30000, 60, 'area da gleba = 3 ha');
    afirma(r.zona === 'ZEU', 'zona detectada pela maior insercao (Art. 22)');
    afirma(!!r.acesso, 'via de acesso reconhecida (Art. 13)');
    console.log(`       ${r.quadra.n} quadras | ${r.lotes.length} lotes | `
      + `verde ${r.verde.area.toFixed(0)} m2 | inst ${r.institucional.area.toFixed(0)} m2`);

    // Art. 39: nenhuma quadra passa de 250 m em qualquer direcao
    afirma(r.quadra.comprimento <= 250 && r.quadra.profundidade <= 250,
      `quadra de ${r.quadra.comprimento} x ${r.quadra.profundidade} m cabe no Art. 39`);

    // Tabela 2: nenhum lote abaixo do minimo
    const pequenos = r.lotes.filter((l) => l.area < 150 - 1e-6);
    afirma(pequenos.length === 0,
      `nenhum lote abaixo de 150 m2 (achei ${pequenos.length})`);
    const estreitos = r.lotes.filter((l) => l.testada < 7.5 - 1e-6);
    afirma(estreitos.length === 0,
      `nenhum lote com testada abaixo de 7,50 m (achei ${estreitos.length})`);

    // Art. 35, I: lote de esquina com testada minima de 10 m
    const esq = r.lotes.filter((l) => l.esquina);
    afirma(esq.length > 0, `${esq.length} lotes de esquina`);
    const esqEstreito = esq.filter((l) => l.testada < 10 - 1e-6);
    afirma(esqEstreito.length === 0,
      `esquinas com testada >= 10 m (Art. 35, I) — irregulares: ${esqEstreito.length}`);

    // a geometria bate com o numero declarado
    for (const l of r.lotes.slice(0, 40))
      perto(areaM(l.anel.map(r.P.back)), l.area, 0.5,
        'area do lote == area do anel desenhado');
  }

  console.log('\n4. INVARIANTE: a soma das partes cabe na gleba');
  {
    G.reset();
    for (const [w, h] of [[200,150],[300,200],[120,90],[500,400]]) {
      const r = G.analisaGleba(gleba(w, h));
      if (!r) continue;
      const soma = r.area_lotes_m2 + r.area_vias_m2 + r.verde.area
                 + r.institucional.area;
      afirma(soma <= r.area_m2 + 1,
        `${w}x${h}: lotes + vias + verde + institucional (${soma.toFixed(0)}) `
        + `cabe na gleba (${r.area_m2.toFixed(0)})`);
      // quadras nunca excedem a gleba
      const aq = r.quadras.reduce((s, q) => s + q.area, 0);
      afirma(aq <= r.area_m2 + 1,
        `${w}x${h}: as quadras cabem na gleba`);
      // e nenhuma quadra se sobrepoe a outra (a malha e disjunta)
      perto(aq, r.area_quadras_m2, 1, `${w}x${h}: area de quadras consistente`);
    }
  }

  console.log('\n5. doacao: percentual da Tabela 2 sobre a base correta');
  {
    G.reset();
    const r = G.analisaGleba(gleba(300, 200));      // 6 ha -> porte de 8%
    perto(r.porte.verde_pct, 8, 0, '6 ha: 8% de area verde');
    perto(r.porte.institucional_pct, 8, 0, '6 ha: 8% de area institucional');
    perto(r.exigido.verde_m2, r.base_doacao_m2 * 0.08, 1,
      'exigencia de verde calculada sobre a base de doacao');
    afirma(r.verde.area >= r.exigido.verde_m2 - 1,
      `verde destinado (${r.verde.area.toFixed(0)}) cobre o exigido `
      + `(${r.exigido.verde_m2.toFixed(0)})`);
    afirma(r.institucional.area >= r.exigido.institucional_m2 - 1,
      `institucional destinado (${r.institucional.area.toFixed(0)}) cobre o `
      + `exigido (${r.exigido.institucional_m2.toFixed(0)})`);
    // Art. 38, III: parcela institucional de no minimo 1.000 m2
    const pi = r.institucional.quadras.filter((q) => q.area < 1000);
    afirma(pi.length === 0,
      `nenhuma parcela institucional abaixo de 1.000 m2 (Art. 38, III)`);
    // sem ZPA na gleba, a base de doacao e a gleba inteira
    perto(r.base_doacao_m2, r.area_m2, 1,
      'sem ZPA, a base de doacao e a gleba inteira');
  }

  console.log('\n6. Art. 21, I: a ZPA sai da base de doacao');
  {
    /* Metade da gleba numa ZPA. O percentual de doacao incide sobre a outra
       metade — se incidisse sobre o todo, o empreendedor doaria area a mais
       por causa de terreno que nem pode parcelar. */
    const meia = [[-2000,-2000],[0,-2000],[0,2000],[-2000,2000],[-2000,-2000]]
      .map(P2);
    const outra = [[0,-2000],[2000,-2000],[2000,2000],[0,2000],[0,-2000]]
      .map(P2);
    const Z2 = {type:'FeatureCollection', features:[
      {type:'Feature', properties:{sigla:'ZEU'},
       geometry:{type:'Polygon', coordinates:[outra]}},
      {type:'Feature', properties:{sigla:'ZPA JENIPARANA'},
       geometry:{type:'Polygon', coordinates:[meia]}}]};
    G.set(Z2, VIAS, {ZEU:{sigla:'ZEU'},
      'ZPA JENIPARANA':{sigla:'ZPA JENIPARANA'}}, lei);
    G.reset();
    // gleba de -100 a +100 em x: metade em cada zona
    const g = [[-100,0],[100,0],[100,150],[-100,150],[-100,0]].map(P2);
    const r = G.analisaGleba(g);
    afirma(r.zpa_pct > 30 && r.zpa_pct < 70,
      `${r.zpa_pct.toFixed(1)}% da gleba em ZPA (esperado ~50%)`);
    afirma(r.base_doacao_m2 < r.area_m2 - 1,
      'a base de doacao e MENOR que a gleba');
    perto(r.base_doacao_m2, r.area_m2 * (1 - r.zpa_pct/100), 1,
      'base = gleba menos a parcela em ZPA');
    afirma(r.varias_zonas, 'o painel sinaliza que a gleba toca duas zonas');
    G.set(ZONA, VIAS, {ZEU:{sigla:'ZEU', familia:'urbana'}}, lei);
  }

  console.log('\n7. as decisoes de projeto mudam o resultado, dentro da lei');
  {
    G.reset();
    const base = G.analisaGleba(gleba(300, 200));
    G.opta({uso: 'interesse_social'});
    const his = G.analisaGleba(gleba(300, 200));
    afirma(his.lote.area_min === 125 && his.lote.testada_min === 5,
      'Interesse Social usa o lote de 125 m2 e testada de 5,00 m');
    afirma(his.lotes.length > base.lotes.length,
      `lote menor rende mais lotes: ${base.lotes.length} -> ${his.lotes.length}`);
    perto(his.porte.verde_pct, 5, 0, 'Interesse Social doa 5% de verde');
    // Art. 35, IV: HIS nao se sujeita a testada de esquina de 10 m
    const esqHis = his.lotes.filter((l) => l.esquina && l.testada < 10);
    afirma(esqHis.length > 0,
      'Art. 35, IV: em HIS a esquina nao precisa dos 10 m');

    G.opta({uso: 'industrial'});
    const ind = G.analisaGleba(gleba(300, 200));
    afirma(ind.lotes.every((l) => l.area >= 1000 - 1e-6),
      'Industrial: nenhum lote abaixo de 1.000 m2');
    afirma(ind.lotes.every((l) => l.testada >= 20 - 1e-6),
      'Industrial: nenhuma testada abaixo de 20 m');
    afirma(ind.lotes.length < base.lotes.length,
      `lote industrial e maior, entao cabem menos: ${ind.lotes.length}`);

    // via mais larga consome mais gleba
    G.reset();
    G.opta({via: 'estrutural'});
    const largo = G.analisaGleba(gleba(300, 200));
    afirma(largo.area_vias_m2 > base.area_vias_m2,
      `via estrutural (19 m) consome mais que a local (10,8 m): `
      + `${base.area_vias_m2.toFixed(0)} -> ${largo.area_vias_m2.toFixed(0)} m2`);
    G.reset();
  }

  console.log('\n8. quadra acima de 250 m e recusada (Art. 39)');
  {
    G.reset();
    G.opta({quadraComprimento_m: 400});
    const r = G.analisaGleba(gleba(600, 200));
    afirma(r.quadra.comprimento <= 250,
      `pedido de 400 m foi limitado a ${r.quadra.comprimento} m`);
    G.reset();
  }

  console.log('\n9. convexidade decide a estrategia de recorte');
  {
    const conv = [[0,0],[100,0],[100,100],[0,100],[0,0]];
    const conc = [[0,0],[100,0],[100,100],[50,50],[0,100],[0,0]];
    afirma(G.ehConvexo(conv) === true, 'retangulo e convexo');
    afirma(G.ehConvexo(conc) === false, 'poligono em L nao e convexo');
    G.reset();
    const r = G.analisaGleba([[0,0],[200,0],[200,150],[100,80],[0,150],[0,0]]
      .map(P2));
    afirma(r && r.convexo === false,
      'gleba concava marcada — o painel avisa que a contagem esta subestimada');
    afirma(r.lotes.every((l) => l.area >= 150 - 1e-6),
      'mesmo em gleba concava, nenhum lote fica abaixo do minimo');
  }

  console.log('\n10. as regras do parcelamento estao no lei.json');
  {
    const p = lei.parcelamento;
    afirma(!!p, 'bloco de parcelamento presente');
    afirma(Object.keys(p.tabela_2).length === 3,
      '3 usos na Tabela 2 (residencial, interesse social, industrial)');
    afirma(p.vias.length === 3, '3 hierarquias viarias na Tabela 3');
    const naoAfere = Object.values(p.regras).filter((r) => !r.aferivel);
    afirma(naoAfere.length >= 5,
      `${naoAfere.length} regras marcadas como NAO afericeis — o painel as `
      + `lista em vez de fingir que verificou`);
    for (const [k, r] of Object.entries(p.regras))
      afirma(!!(r.artigo && r.texto), `regra "${k}" cita artigo e texto`);
    afirma(!!p.condominio && p.condominio.verde_pct.ate_62500 === 8,
      'condominio tem percentuais proprios (Art. 46), nao os da Tabela 2');
  }

  console.log('\n' + (falhas ? `${falhas} FALHA(S)` : 'todos os testes passaram'));
  process.exit(falhas ? 1 : 0);
})().catch((e) => { console.error('ERRO NO TESTE:', e); process.exit(1); });

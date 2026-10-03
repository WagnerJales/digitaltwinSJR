/* =====================================================================
   Testes do motor de geometria do cliente (web/index.html).

       node tests/test_geometria.js

   Requer apenas Node — nenhuma dependência. Extrai os blocos de geometria
   direto do index.html e roda contra valores analíticos conhecidos e
   contra a saída do pipeline Python, que é a referência.

   Por que existe: o cálculo de área, o recorte pelo afastamento frontal e
   a detecção de zona rodam no navegador, sem servidor. Um erro silencioso
   aqui produz um estudo de viabilidade errado com aparência de correto.
   Este arquivo já pegou um bug de centroide que jogava o ponto de consulta
   para fora do lote.
   ===================================================================== */
const fs = require('fs');
const path = require('path');

const RAIZ = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(__dirname, '..', 'web', 'index.html'), 'utf8');

function fatia(ini, fim) {
  const a = html.indexOf(ini);
  const b = html.indexOf(fim, a);
  if (a < 0 || b < 0) {
    console.error(`ERRO: nao achei o bloco "${ini.slice(0, 40)}" em index.html.`);
    console.error('Os marcadores mudaram? Ajuste este teste.');
    process.exit(2);
  }
  return html.slice(a, b);
}

// bloco de geometria: entre areaTxt() e o map.on('load')
const geom = fatia('const M_LAT = 110574.0;', "map.on('load'");
// expansor do formato compacto dos enderecos: fica antes do bloco de
// geometria, junto de SRC(), mas e testado com o mesmo codigo que o app usa
const enderecos = fatia('function expandeEnderecos(c){', '// BASEMAPS raster');
// da declaração do lote até desenhaLote(): analisaLote + blocoEnvelope
const analise = fatia('let loteRing = [];', 'function desenhaLote()');

const G = new Function(`
  const PE_DIREITO_M = 3.0;
  let ZONAS_FC = null, VIAS_FC = null, PARAMS = {}, LEI = null;
  // stubs de formatacao usados nas mensagens de restricao
  const fmt = (n,d=0) => Number(n).toFixed(d);
  const areaTxt = m => Number(m).toFixed(1) + ' m2';
  ${enderecos}
  ${geom}
  ${analise}
  return { areaAnelM2, pontoNoAnel, recortaSemiplano, shoelace, fecha, proj,
           centroideAnel, pontoInterno, analisaLote, zonaEm, frentesDoLote,
           viaMaisProxima, blocoEnvelope, bboxAnel,
           leiDaZona, afastamentosPara, simulaGabarito, maxGabaritoViavel,
           recortaPorAfastamentos, gabaritoLegal, aplicaAjustes,
           ajusta: o => { ajustes = {pe_direito_m:PE_DIREITO_M, ...o}; },
           campos: () => Object.keys(ajustes),
           opta: o => { opcoes = {podio:true, empenaCega:false,
                                  ladoEmpena:null, pilotis:false,
                                  pavGaragem:0, coberturaUnidades:false,
                                  regimeLote:'comum', ...o}; },
           afastamentosAte15m, melhorLateral, lateraisDisponiveis,
           lateralDaEmpena, leiEfetiva, intersectaAnel, expandeEnderecos,
           COR_PAV,
           PE: PE_DIREITO_M, GAP: GAP_PAV_M,
           // zera os caches ao trocar de cenario, senao o indice de vias e
           // os bbox das zonas do cenario anterior contaminam o proximo
           set: (z,v,p,l) => { ZONAS_FC=z; VIAS_FC=v; PARAMS=p;
                               if(l !== undefined) LEI=l;
                               _zbox = null; _viaGrid = null; } };
`)();

const proc = n => JSON.parse(
  fs.readFileSync(path.join(RAIZ, 'data', 'processados', n), 'utf8'));

let falhas = 0;
function perto(a, b, tol, msg) {
  const ok = Math.abs(a - b) <= tol;
  if (!ok) falhas++;
  console.log(`${ok ? '  ok  ' : ' FALHA'} ${msg}: ${a.toFixed(2)} `
              + `(esperado ${b.toFixed(2)} ±${tol})`);
}
function afirma(cond, msg) {
  if (!cond) falhas++;
  console.log(`${cond ? '  ok  ' : ' FALHA'} ${msg}`);
}

// ---------------------------------------------------------------- 1
console.log('1. area de retangulo sintetico');
const lat0 = -2.5615, lon0 = -44.054;
const gl = m => m / (111320 * Math.cos(lat0 * Math.PI / 180));
const gt = m => m / 110574;
const ret = [[lon0, lat0], [lon0 + gl(12.5), lat0],
             [lon0 + gl(12.5), lat0 + gt(40)], [lon0, lat0 + gt(40)],
             [lon0, lat0]];
perto(G.areaAnelM2(ret), 500, 0.5, 'retangulo 12,5 x 40 m');

// ---------------------------------------------------------------- 2
console.log('\n2. recorte por semiplano (afastamento frontal)');
const q = [[0,0],[20,0],[20,20],[0,20],[0,0]];
perto(Math.abs(G.shoelace(G.recortaSemiplano(q, 0, 1, -3))), 340, 1e-9,
      'quadrado 20x20 recuado 3 m');
perto(Math.abs(G.shoelace(G.recortaSemiplano(q, 0, 1, 0))), 400, 1e-9,
      'recuo zero preserva a area');
afirma(G.recortaSemiplano(q, 0, 1, -25).length === 0,
       'recuo maior que o lote devolve poligono vazio');

// ---------------------------------------------------------------- 3
console.log('\n3. ponto em anel');
for (const [x, y, esp] of [[10,10,true],[-1,10,false],[10,25,false],[19.9,0.1,true]])
  afirma(G.pontoNoAnel(x, y, q) === esp, `ponto (${x},${y}) dentro=${esp}`);

// ---------------------------------------------------------------- 4
console.log('\n4. centroide e ponto interno em poligono concavo');
// L de 20x20 com o quadrante superior direito removido: o centroide de
// area cai FORA da figura, e pontoInterno tem de corrigir isso
const Lshape = [[0,0],[20,0],[20,10],[10,10],[10,20],[0,20],[0,0]];
perto(Math.abs(G.shoelace(Lshape)), 300, 1e-9, 'area do L');
const ci = G.pontoInterno(Lshape);
afirma(G.pontoNoAnel(ci[0], ci[1], Lshape), 'pontoInterno cai dentro do L');

// ---------------------------------------------------------------- 5
console.log('\n5. areas das 13 zonas da lei: cliente vs pipeline Python');
const zon = proc('zoneamento.geojson');
// a lei entra desde aqui: os afastamentos da Tabela 8 valem em todo o
// municipio, inclusive nas zonas fora da Tabela 7
G.set(zon, proc('vias.geojson'), proc('parametros.json'), proc('lei.json'));
let pior = 0, piorZona = '';
for (const f of zon.features) {
  const polys = f.geometry.type === 'Polygon' ? [f.geometry.coordinates]
                                              : f.geometry.coordinates;
  let a = 0;
  for (const poly of polys)
    poly.forEach((ring, i) => { a += (i === 0 ? 1 : -1) * G.areaAnelM2(ring); });
  const dif = Math.abs(a - f.properties.area_m2) / f.properties.area_m2 * 100;
  if (dif > pior) { pior = dif; piorZona = f.properties.sigla; }
}
afirma(pior < 0.5,
       `maior divergencia ${pior.toFixed(4)}% (${piorZona}) — limite 0,5%`);

// ---------------------------------------------------------------- 6
console.log('\n6. estudo de viabilidade num lote da Zona Central');
/* Ancora num endereco que o pipeline classificou como ZC, mas nao em
   qualquer um. Dois filtros, cada um por um motivo:

   - o lote de teste tem 40 m de fundo e, perto da divisa, invade a ZS.
     Exigimos que o lote INTEIRO caia na ZC, senao estariamos testando o
     detector de zona contra um lote que de fato esta a cavaleiro de duas;

   - a Zona Central e miuda e cheia de esquina. Num lote de 3 testadas o
     art. 112 manda aplicar afastamento frontal nas tres, e os 12,5 m de
     largura se esgotam: envelope zero. E resultado correto, mas nao serve
     para verificar o invariante "envelope menor que o lote e nao vazio".
     Aqui queremos um lote de meio de quadra; a esquina e exercitada com
     geometria sintetica na secao 8. */
const loteAoRedor = c => {
  const dl = 12.5 / (111320 * Math.cos(c[1] * Math.PI / 180)), dt = 40 / 110574;
  return [[c[0],c[1]], [c[0]+dl,c[1]], [c[0]+dl,c[1]+dt], [c[0],c[1]+dt]];
};
const alvo = G.expandeEnderecos(proc('enderecos.json'))
  .features.find(f => {
  if (f.properties.zona !== 'ZC') return false;
  const t = G.analisaLote(loteAoRedor(f.geometry.coordinates));
  return t.zonas_tocadas.every(z => z === 'ZC') && !t.esquina;
});
if (!alvo) {
  console.log('  (sem endereco em ZC no recorte — teste pulado)');
} else {
  const c = alvo.geometry.coordinates;
  const r = G.analisaLote(loteAoRedor(c));
  console.log(`       zona ${r.zona} | area ${r.area_m2.toFixed(1)} m2 | `
            + `testada ${r.testada_m.toFixed(1)} m | afast ${r.afastamento_m} m | `
            + `gabarito ${r.pavimentos} pav | via ${r.via_principal || 'sem nome'} | `
            + `desalinhamento ${r.frentes[0].ang.toFixed(1)}deg`);
  afirma(r.zona === 'ZC', 'zona detectada corretamente');
  perto(r.area_m2, 500, 0.5, 'area do lote');
  // Com via real, o recuo sai perpendicular ao EIXO DA RUA, que raramente e
  // paralelo a um retangulo sintetico — por isso aqui so verificamos
  // invariantes. O valor exato do recuo e testado na secao 8, com vias
  // sinteticas de orientacao conhecida.
  afirma(r.frentes.length >= 1, 'testada reconhecida a partir de via real');
  afirma(r.area_envelope_m2 > 0 && r.area_envelope_m2 < r.area_m2,
         'envelope menor que o lote e nao vazio (afastamento 3 m)');
  /* A area construivel NAO e envelope x pavimentos: o envelope de referencia
     usa os afastamentos do terreo, e o gabarito maximo usa os da sua faixa,
     alem dos tetos de ATME e taxa de ocupacao. O invariante certo e que ela
     coincide com a simulacao no gabarito maximo e respeita a ATME. */
  perto(r.area_construivel_m2, r.sim_max.area_construida_m2, 1e-6,
        'construivel = simulacao no gabarito maximo');
  afirma(r.area_construivel_m2 <= r.area_m2 * 2.4 + 1e-6,
         'construivel respeita a ATME de 240% da ZC');
  afirma(r.area_construivel_m2 > 0, 'ha area construivel');

  // lote em L ancorado no mesmo ponto: exercita pontoInterno com dado real
  const s = 10 / (111320 * Math.cos(c[1] * Math.PI / 180)), t = 10 / 110574;
  const rl = G.analisaLote([[c[0],c[1]], [c[0]+2*s,c[1]], [c[0]+2*s,c[1]+t],
                            [c[0]+s,c[1]+t], [c[0]+s,c[1]+2*t], [c[0],c[1]+2*t]]);
  perto(rl.area_m2, 300, 1, 'area do lote em L');
  afirma(rl.zona === 'ZC', 'zona do lote concavo detectada');
  /* O que este caso exercita e o pontoInterno num poligono concavo com dado
     real — e isso passa. O envelope da ZERO, e o resultado certo: o L de
     300 m2 caiu numa esquina com 3 testadas, e o art. 112 manda afastamento
     frontal em cada uma. 3 x 5 m de frontal mais lateral e fundos nao deixam
     projecao. Exigir envelope > 0 aqui seria exigir que o app mentisse. */
  afirma(rl.area_envelope_m2 >= 0
         && rl.area_envelope_m2 <= rl.area_m2 + 1e-6,
         'envelope do lote concavo e um numero valido');
  if(rl.frentes.length >= 3)
    afirma(rl.area_envelope_m2 === 0,
           `lote de ${rl.frentes.length} testadas: os afastamentos frontais `
           + `consomem o terreno, e o app diz isso em vez de arredondar`);
}

// ---------------------------------------------------------------- 7
console.log('\n7. bloco 3D da possibilidade construtiva');
{
  // envelope quadrado de 20x20 = 400 m2, gabarito 4 pavimentos
  const s = { envelope: [[0,0],[0,1],[1,1],[1,0],[0,0]], pavimentos: 4,
              area_envelope_m2: 400 };

  const emp = G.blocoEnvelope(s, 4, true);
  afirma(emp.length === 4, 'empilhado gera uma feicao por pavimento');
  afirma(emp.every(f => f.properties.tipo === 'computavel'),
         '4 pavimentos no gabarito 4 sao todos computaveis');
  afirma(emp.every(f => f.properties.computa === true),
         'sem garagem/pilotis/cobertura, todo pavimento consome ATME');
  const alturasOk = emp.every((f, i) =>
    Math.abs(f.properties.base_m - i * G.PE) < 1e-9 &&
    Math.abs(f.properties.topo_m - ((i+1) * G.PE - G.GAP)) < 1e-9);
  afirma(alturasOk, 'base/topo de cada pavimento empilham corretamente');
  afirma(emp[0].properties.base_m === 0, 'primeiro pavimento apoia no solo');

  const massa = G.blocoEnvelope(s, 4, false);
  afirma(massa.length === 1, 'massa unica gera uma feicao so');
  perto(massa[0].properties.topo_m, 12, 1e-9, 'altura da massa (4 x 3 m)');

  // acima do gabarito: pavimentos excedentes marcados
  const exc = G.blocoEnvelope(s, 6, true);
  afirma(exc.length === 6, 'simulacao acima do gabarito gera 6 pavimentos');
  afirma(exc.filter(f => f.properties.tipo === 'excedente').length === 2,
         'exatamente 2 pavimentos marcados como excedente');
  afirma(exc.slice(0,4).every(f => f.properties.tipo === 'computavel'),
         'os 4 primeiros continuam legais');

  // casos-limite
  afirma(G.blocoEnvelope(s, 0, true).length === 0, 'zero pavimentos: bloco vazio');
  afirma(G.blocoEnvelope(null, 4, true).length === 0, 'sem estudo: bloco vazio');
  afirma(G.blocoEnvelope({envelope:null, pavimentos:4}, 4, true).length === 0,
         'sem envelope: bloco vazio');
  // zona sem gabarito na lei: os pavimentos sao INDETERMINADOS, nao
  // excedentes — nao ha limite legal a exceder
  const semGab = G.blocoEnvelope(
    {envelope:s.envelope, pavimentos:null, area_envelope_m2:400}, 3, true);
  afirma(semGab.length === 3 &&
         semGab.every(f => f.properties.tipo === 'indeterminado'),
         'zona sem gabarito: pavimentos indeterminados, nao excedentes');

  const bb = G.bboxAnel([[10,20],[12,25],[11,22],[10,20]]);
  afirma(bb[0][0] === 10 && bb[0][1] === 20 && bb[1][0] === 12 && bb[1][1] === 25,
         'bboxAnel enquadra o lote');
}

// ---------------------------------------------------------------- 8
console.log('\n8. reconhecimento do eixo viario e afastamento');
{
  /* Cenario sintetico e controlado: uma zona quadrada de 1 km, parametros
     conhecidos e vias que eu mesmo posiciono. Assim da para saber a
     resposta exata e verificar se o recuo sai perpendicular ao EIXO DA VIA
     — nao a aresta desenhada. */
  const O = [-44.06, -2.57];                       // origem local
  const KX = 111320 * Math.cos(O[1] * Math.PI / 180), KY = 110574;
  const P2 = ([x, y]) => [O[0] + x / KX, O[1] + y / KY];   // metros -> lon/lat
  const rot = (p, g) => {
    const r = g * Math.PI / 180, c = Math.cos(r), s = Math.sin(r);
    return [p[0] * c - p[1] * s, p[0] * s + p[1] * c];
  };

  const zonaQuad = [[-500,-500],[500,-500],[500,500],[-500,500],[-500,-500]].map(P2);
  const ZONA = {type:'FeatureCollection', features:[{type:'Feature',
    properties:{sigla:'TESTE'}, geometry:{type:'Polygon', coordinates:[zonaQuad]}}]};
  const PAR = {TESTE:{sigla:'TESTE', area_min_m2:150, testada_min_m:7.5}};
  const LEI8 = proc('lei.json');
  // afastamento frontal do terreo pela Tabela 8 — vale para todo o municipio
  const AF = LEI8.afastamentos_por_gabarito[0].frontal_m;   // 5,0 m
  const via = (pts, nome) => ({type:'Feature',
    properties:{nome, tipo_osm:'residential'},
    geometry:{type:'LineString', coordinates:pts.map(P2)}});

  // ---- 8a. lote alinhado, uma frente ----
  G.set(ZONA, {type:'FeatureCollection',
    features:[via([[-200,-6],[200,-6]], 'Rua Teste')]}, PAR, LEI8);
  const lote = [[0,0],[12.5,0],[12.5,40],[0,40]].map(P2);
  let r = G.analisaLote(lote);
  afirma(r.frentes.length === 1, 'lote alinhado: uma testada');
  afirma(r.via_principal === 'Rua Teste', 'nome da via reconhecido');
  perto(r.testada_m, 12.5, 0.2, 'testada = aresta paralela a via');
  perto(r.frentes[0].ang, 0, 0.5, 'desalinhamento ~0 grau');
  perto(r.afastamento_m, AF, 0, 'afastamento vem da Tabela 8');
  /* Esta secao testa o ALINHAMENTO: se o recuo frontal sai perpendicular ao
     EIXO DA VIA. Por isso mede `area_alinhamento_m2`, o recorte so pelo
     frontal. O envelope do terreo (`area_envelope_m2`) recua tambem lateral
     e fundos e ainda obedece a ALML — e verificado na secao 11c. */
  perto(r.area_alinhamento_m2, 500 - 12.5 * AF, 1.0,
        `alinhamento = 500 - 12,5 x ${AF}`);
  afirma(r.area_envelope_m2 < r.area_alinhamento_m2,
         'o envelope do terreo e menor: soma lateral, fundos e ALML');
  afirma(!r.esquina, 'nao e esquina');

  // ---- 8b. a frente nao e simplesmente a aresta mais proxima ----
  // via ao NORTE, mais perto da aresta de cima: a frente tem de mudar de lado
  G.set(ZONA, {type:'FeatureCollection',
    features:[via([[-200,46],[200,46]], 'Rua Norte')]}, PAR, LEI8);
  r = G.analisaLote(lote);
  afirma(r.frentes.length === 1 && r.frentes[0].i === 2,
         'via ao norte: a testada passa a ser a aresta norte');

  // ---- 8c. aresta perpendicular perto da via NAO e testada ----
  // via vertical colada na lateral esquerda do lote
  G.set(ZONA, {type:'FeatureCollection',
    features:[via([[-4,-50],[-4,90]], 'Rua Lateral')]}, PAR, LEI8);
  r = G.analisaLote(lote);
  const lateral = r.arestas.find(a => a.i === 3);   // aresta oeste (vertical)
  afirma(lateral && lateral.frente,
         'aresta paralela a via lateral e reconhecida como testada');
  const inferior = r.arestas.find(a => a.i === 0); // aresta sul (horizontal)
  afirma(inferior && !inferior.frente,
         'aresta perpendicular ao eixo nao vira testada');

  // ---- 8d. lote de esquina: duas frentes, dois recuos ----
  G.set(ZONA, {type:'FeatureCollection', features:[
    via([[-200,-6],[200,-6]], 'Rua Sul'),
    via([[-6,-200],[-6,200]], 'Rua Oeste')]}, PAR, LEI8);
  const quadra = [[0,0],[20,0],[20,20],[0,20]].map(P2);
  r = G.analisaLote(quadra);
  afirma(r.esquina && r.frentes.length === 2, 'esquina: duas testadas');
  const nomes = r.frentes.map(f => f.via.nome).sort();
  afirma(nomes[0] === 'Rua Oeste' && nomes[1] === 'Rua Sul',
         'as duas vias da esquina sao identificadas');
  // Art. 112: um afastamento frontal por testada. 20x20 com AF em duas faces
  perto(r.area_alinhamento_m2, (20 - AF) * (20 - AF), 1.5,
        `esquina: recuo de ${AF} m aplicado nas duas frentes`);

  // ---- 8e. lote TORTO: o recuo segue o eixo, nao a aresta ----
  // Terreno girado 20 graus, via na horizontal. O plano de recuo tem de ser
  // horizontal (perpendicular a normal do eixo), nao girado com o lote.
  const ang = 20;
  const cantos = [[0,0],[12.5,0],[12.5,40],[0,40]].map(p => rot(p, ang));
  const yMin = Math.min(...cantos.map(p => p[1]));
  G.set(ZONA, {type:'FeatureCollection',
    features:[via([[-300, yMin - 5], [300, yMin - 5]], 'Rua Torta')]}, PAR, LEI8);
  r = G.analisaLote(cantos.map(P2));
  afirma(r.frentes.length >= 1, 'lote torto: testada encontrada');

  // Oraculo independente: Monte Carlo. A via e horizontal, entao o recuo
  // legal e a faixa y >= (menor y da testada) + AF. Nada aqui usa o codigo
  // sob teste para decidir a normal.
  const fr0 = r.frentes[0];
  const yTest = Math.min(cantos[fr0.i][1], cantos[(fr0.i + 1) % 4][1]);
  const corte = yTest + AF;
  const xs = cantos.map(p => p[0]), ys = cantos.map(p => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const y0 = Math.min(...ys), y1 = Math.max(...ys);
  const anelM = G.fecha(cantos);
  let dentro = 0;
  const N = 400000;
  for (let k = 0; k < N; k++) {
    const x = x0 + Math.random() * (x1 - x0);
    const y = y0 + Math.random() * (y1 - y0);
    if (y >= corte && G.pontoNoAnel(x, y, anelM)) dentro++;
  }
  const esperadoMC = dentro / N * (x1 - x0) * (y1 - y0);
  console.log(`       Monte Carlo (${N.toLocaleString('pt-BR')} amostras): `
            + `${esperadoMC.toFixed(1)} m2 | codigo: `
            + `${r.area_alinhamento_m2.toFixed(1)} m2`);
  perto(r.area_alinhamento_m2, esperadoMC, 4,
        'lote torto: recuo perpendicular ao eixo');

  // e o recuo NAO pode coincidir com o da aresta (que daria 500 - 12,5 x AF)
  afirma(Math.abs(r.area_alinhamento_m2 - (500 - 12.5 * AF)) > 2,
         `recuo do lote torto difere do recuo pela aresta (${500 - 12.5*AF})`);

  // ---- 8f. sem via por perto ----
  G.set(ZONA, {type:'FeatureCollection',
    features:[via([[-400,-400],[-390,-400]], 'Rua Longe')]}, PAR, LEI8);
  r = G.analisaLote(lote);
  afirma(r.frente_inferida || r.frentes.length === 0,
         'via distante: frente marcada como inferida');
}

// ---------------------------------------------------------------- 9
console.log('\n9. modelo legal (Lei Complementar 77/2025)');
{
  const lei = proc('lei.json');
  const O = [-44.06, -2.57];
  const KX = 111320 * Math.cos(O[1] * Math.PI / 180), KY = 110574;
  const P2 = ([x, y]) => [O[0] + x / KX, O[1] + y / KY];
  const quad = [[-500,-500],[500,-500],[500,500],[-500,500],[-500,-500]].map(P2);

  // ZC: Tabela 7 do autografo -> ATME 240%, ALML 30%, altura 15 m
  const ZONA = {type:'FeatureCollection', features:[{type:'Feature',
    properties:{sigla:'ZC'}, geometry:{type:'Polygon', coordinates:[quad]}}]};
  const VIAS = {type:'FeatureCollection', features:[{type:'Feature',
    properties:{nome:'Rua Teste', tipo_osm:'residential'},
    geometry:{type:'LineString', coordinates:[[-300,-6],[300,-6]].map(P2)}}]};
  G.set(ZONA, VIAS, {ZC:{sigla:'ZC'}}, lei);

  afirma(G.leiDaZona('ZC') !== null, 'ZC tem linha na Tabela 7');
  afirma(G.leiDaZona('ZPA JENIPARANA') === null,
         'ZPA Jeniparana tem memorial mas nao tem linha na Tabela 7');
  afirma(G.leiDaZona('ZAAJ') === null,
         'ZAAJ nao existe na lei sancionada');
  const zc = G.leiDaZona('ZC');
  perto(zc.atme_pct, 240, 0, 'ATME da ZC = 240%');
  perto(zc.taxa_ocupacao_max_pct, 70, 0, 'ocupacao maxima ZC = 100 - ALML');
  perto(zc.altura_max_m, 15, 0, 'altura maxima ZC = 15 m');

  // Tabela 8 tabelada: ate 5 pavimentos
  perto(G.afastamentosPara(1).lateral_m, 1.5, 0, 'Tabela 8: 1 pav -> lateral 1,5');
  perto(G.afastamentosPara(2).lateral_m, 2.0, 0, 'Tabela 8: 2 pav -> lateral 2,0');
  perto(G.afastamentosPara(4).lateral_m, 3.0, 0, 'Tabela 8: 3a5 pav -> lateral 3,0');
  perto(G.afastamentosPara(8).frontal_m, 6.0, 0, 'Tabela 8: 6a10 pav -> frontal 6,0');
  afirma(G.afastamentosPara(31) === null, 'Tabela 8 nao cobre 31 pavimentos');

  /* Acima do 5o pavimento a Tabela 8 grafa "*" e manda calcular pelo
     art. 111: base de 3,00 m (ultimo valor tabelado) + acrescimo por
     pavimento contado a partir do quinto. */
  perto(G.afastamentosPara(6).lateral_m, 3.65, 1e-9,
        'art. 111 II: 6 pav -> 3,00 + 1 x 0,65 = 3,65 m');
  perto(G.afastamentosPara(10).lateral_m, 6.25, 1e-9,
        'art. 111 II: 10 pav -> 3,00 + 5 x 0,65 = 6,25 m');
  perto(G.afastamentosPara(11).lateral_m, 6.30, 1e-9,
        'art. 111 III: 11 pav -> 3,00 + 6 x 0,55 = 6,30 m');
  perto(G.afastamentosPara(20).lateral_m, 11.25, 1e-9,
        'art. 111 III: 20 pav -> 3,00 + 15 x 0,55 = 11,25 m');
  perto(G.afastamentosPara(30).lateral_m, 14.25, 1e-9,
        'art. 111 IV: 30 pav -> 3,00 + 25 x 0,45 = 14,25 m');
  // dentro de uma mesma faixa os valores diferem: por isso a consulta e
  // pavimento a pavimento, nao por faixa
  afirma(G.afastamentosPara(6).lateral_m !== G.afastamentosPara(10).lateral_m,
         'na faixa 6a10 o afastamento varia pavimento a pavimento');
  /* A lei tem uma descontinuidade real no 21o pavimento: o acrescimo cai de
     0,55 para 0,45 e o afastamento DIMINUI. Esta aplicada como escrita. */
  afirma(G.afastamentosPara(21).lateral_m < G.afastamentosPara(20).lateral_m,
         'descontinuidade do art. 111 no 21o pavimento reproduzida fielmente');
  // o frontal nao recebe acrescimo: a nota "*" so marca lateral e fundos
  perto(G.afastamentosPara(10).frontal_m, 6.0, 0,
        'frontal de 6a10 fica em 6,0 m, sem acrescimo');

  // lote grande: 40 x 50 = 2000 m2, frente ao sul
  const lote = [[0,0],[40,0],[40,50],[0,50]].map(P2);
  const r = G.analisaLote(lote);
  afirma(r.lei !== null, 'estudo carrega os parametros legais');
  perto(r.area_m2, 2000, 3, 'area do lote');
  perto(r.area_min_m2, 150, 0, 'area minima vem da Tabela 7 (150 m2)');
  perto(r.testada_min_m, 7.5, 0, 'testada minima vem da Tabela 7 (7,5 m)');

  console.log(`       gabarito maximo viavel: ${r.pavimentos} pav | `
            + `gabarito legal ${r.gabarito_legal} | `
            + `construivel ${r.area_construivel_m2.toFixed(0)} m2 | `
            + `ATME max ${(r.area_m2*2.4).toFixed(0)} m2`);

  /* O gabarito e definido pela LEI: altura maxima / pe-direito (Art. 114).
     ZC tem 15 m; com pe-direito de 3,00 m cabem 5 pavimentos. */
  afirma(r.gabarito_legal === 5, 'gabarito legal ZC = 15 m / 3,00 m = 5 pav');
  afirma(r.pavimentos === 5,
         'gabarito viavel = 5 (lote grande comporta os afastamentos)');
  afirma(r.altura_m <= 15 + 1e-6, 'altura do gabarito nao excede a da zona');
  afirma(r.area_construivel_m2 <= r.area_m2 * 2.4 + 1e-6,
         'area construivel nao ultrapassa a ATME de 240%');

  /* REGRESSAO: atingir a ATME limita AREA, nunca o numero de pavimentos.
     Antes o codigo travava o gabarito ao bater na ATME — errado. */
  const s5 = G.simulaGabarito(r, 5);
  afirma(s5.excede_atme === true, '5 pav atinge a ATME (cenario do teste)');
  afirma(s5.bloqueios.length === 0,
         'ATME atingida NAO bloqueia o gabarito');
  afirma(s5.limites.some(x => x.tipo === 'atme'),
         'ATME aparece como limite de area, nao como bloqueio');
  afirma(s5.envelope !== null, 'envelope existe mesmo com ATME atingida');
  perto(s5.area_construida_m2, r.area_m2 * 2.4, 1,
        'area construida travada exatamente na ATME');

  // e a taxa de ocupacao tambem nao bloqueia
  const s3 = G.simulaGabarito(r, 3);
  if(s3.limitado_por_to)
    afirma(s3.bloqueios.length === 0,
           'taxa de ocupacao atingida NAO bloqueia o gabarito');

  // pe-direito menor => mais pavimentos na mesma altura
  afirma(G.gabaritoLegal(zc, 2.60) === 5, 'pe-direito 2,60 m -> 5 pav em 15 m');
  afirma(G.gabaritoLegal(zc, 4.00) === 3, 'pe-direito 4,00 m -> 3 pav em 15 m');
  const zeu = G.leiDaZona('ZEU');
  afirma(G.gabaritoLegal(zeu, 3.00) === 20, 'ZEU (60 m / 3,00 m) -> 20 pav');
  afirma(G.gabaritoLegal(zeu, 2.60) === 23, 'ZEU (60 m / 2,60 m) -> 23 pav');

  // afastamentos crescem com o gabarito -> projecao diminui
  const s2 = G.simulaGabarito(r, 2), s8 = G.simulaGabarito(r, 8);
  afirma(s8.area_projecao_bruta_m2 < s2.area_projecao_bruta_m2,
         'mais pavimentos -> afastamentos maiores -> projecao menor');
  console.log(`       projecao: 2 pav ${s2.area_projecao_bruta_m2.toFixed(0)} m2 `
            + `-> 8 pav ${s8.area_projecao_bruta_m2.toFixed(0)} m2`);

  // taxa de ocupacao: projecao nunca passa de 70% do lote
  afirma(s2.area_projecao_m2 <= r.area_m2 * 0.70 + 1e-6,
         'projecao respeita a taxa de ocupacao de 70%');
  afirma(s2.limitado_por_to === true,
         'projecao bruta de 2 pav excede 70% e e travada pela ALML');

  // altura acima de 15 m e o UNICO bloqueio de gabarito por parametro de zona
  const s6 = G.simulaGabarito(r, 6);          // 18 m
  afirma(s6.bloqueios.some(x => x.tipo === 'altura'),
         '6 pav (18 m) viola a altura maxima de 15 m — bloqueio real');

  // lote minusculo: afastamentos consomem tudo
  const mini = [[0,0],[8,0],[8,8],[0,8]].map(P2);
  const rm = G.analisaLote(mini);
  afirma(rm.pavimentos === 0 || rm.area_construivel_m2 === 0,
         'lote de 8x8 nao comporta os afastamentos: gabarito 0');
  afirma(rm.ok_area === false, 'lote de 64 m2 reprova na area minima de 150 m2');

  /* Zona ambiental: tem memorial descritivo na Tabela 1, mas a Tabela 7 nao
     lhe da linha. Os afastamentos da Tabela 8 e a permeabilidade do Art. 98
     valem em todo o municipio e continuam sendo aplicados; ATME, ALML e
     altura maxima simplesmente nao existem para ela. Indeterminado nao e
     liberado, e tambem nao e zero. */
  const ZONA2 = {type:'FeatureCollection', features:[{type:'Feature',
    properties:{sigla:'ZPA JENIPARANA'},
    geometry:{type:'Polygon', coordinates:[quad]}}]};
  G.set(ZONA2, VIAS, {'ZPA JENIPARANA':{sigla:'ZPA JENIPARANA'}}, lei);
  const r2 = G.analisaLote(lote);
  afirma(r2.lei === null, 'ZPA Jeniparana: sem linha na Tabela 7');
  afirma(r2.pavimentos === null, 'gabarito INDETERMINADO — o app nao arbitra');
  afirma(r2.area_construivel_m2 === null,
         'sem gabarito legal nao ha area construivel a informar');
  afirma(r2.area_min_m2 === null,
         'sem Tabela 7 nao ha area minima aferivel');
  afirma(r2.ok_area === null, 'conformidade de area indeterminada');
  perto(r2.afastamento_m, 5, 0,
        'afastamento vem da Tabela 8 mesmo sem Tabela 7');
  const sl = G.simulaGabarito(r2, 3);
  afirma(sl.sem_tabela7 === true, 'simulacao marcada como fora da Tabela 7');
  afirma(sl.afastamentos !== null,
         'Tabela 8 aplicada normalmente na zona sem Tabela 7');
  afirma(sl.bloqueios.length === 0,
         'sem altura maxima definida nao ha bloqueio de altura');
  afirma(sl.area_construida_m2 > 0, 'ainda assim ha estudo geometrico');
  afirma(lei.zonas_sem_parametro['ZPA JENIPARANA'],
         'a lei.json nomeia a zona sem parametro, para o painel explicar');
}

// ---------------------------------------------------------------- 10
console.log('\n10. Tabela 7 INTEIRA e imutavel; so o pe-direito e ajustavel');
{
  const lei = proc('lei.json');
  const O = [-44.06, -2.57];
  const KX = 111320 * Math.cos(O[1] * Math.PI / 180), KY = 110574;
  const P2 = ([x, y]) => [O[0] + x / KX, O[1] + y / KY];
  const quad = [[-500,-500],[500,-500],[500,500],[-500,500],[-500,-500]].map(P2);
  const VIAS = {type:'FeatureCollection', features:[{type:'Feature',
    properties:{nome:'Rua Teste', tipo_osm:'residential'},
    geometry:{type:'LineString', coordinates:[[-300,-6],[300,-6]].map(P2)}}]};
  const lote = [[0,0],[40,0],[40,50],[0,50]].map(P2);

  // --- zona COM lei (ZC): sem ajuste, tudo vem da norma ---
  const ZC = {type:'FeatureCollection', features:[{type:'Feature',
    properties:{sigla:'ZC'}, geometry:{type:'Polygon', coordinates:[quad]}}]};
  G.set(ZC, VIAS, {ZC:{sigla:'ZC'}}, lei);
  G.ajusta({});
  let r = G.analisaLote(lote);
  afirma(r.lei.origem === 'lei', 'sem ajuste: origem = lei');
  afirma(r.lei.alterado.length === 0, 'sem ajuste: nada marcado como alterado');
  perto(r.lei.atme_pct, 240, 0, 'ATME da lei preservada');

  /* REGRESSAO: nenhum parametro da Tabela 7 e ajustavel. O app adota o que
     esta na lei. So o pe-direito, que e premissa de projeto, e editavel. */
  const ajustaveis = G.campos();
  for(const campo of ['atme_pct','alml_pct','altura_max_m',
                      'area_min_m2','testada_min_m'])
    afirma(!ajustaveis.includes(campo), `${campo} nao e campo ajustavel`);
  afirma(ajustaveis.length === 1 && ajustaveis[0] === 'pe_direito_m',
         'so o pe-direito e ajustavel');

  // forcar qualquer parametro da Tabela 7 nao surte efeito
  G.ajusta({atme_pct: 800, alml_pct: 60, altura_max_m: 45});
  r = G.analisaLote(lote);
  perto(r.lei.atme_pct, 240, 0, 'ATME continua a da lei mesmo se forcada');
  perto(r.lei.taxa_ocupacao_max_pct, 70, 0,
        'ocupacao continua a da lei mesmo se ALML for forcada');
  perto(r.lei.altura_max_m, 15, 0, 'altura continua a da lei mesmo se forcada');
  afirma(r.gabarito_legal === 5,
         'gabarito continua 5 (15 m da lei), nao 15 (45 m forcados)');
  afirma(r.lei.origem === 'lei', 'estudo permanece marcado como "lei"');
  afirma(r.lei.alterado.length === 0, 'nada aparece como alterado');
  afirma(r.area_construivel_m2 <= r.area_m2 * 2.4 + 1e-6,
         'ATME da lei (240%) continua limitando a area');

  // --- pe-direito ajustado muda o gabarito sem mexer na lei ---
  G.ajusta({pe_direito_m: 2.60});
  r = G.analisaLote(lote);
  afirma(r.gabarito_legal === 5, 'ZC com pe-direito 2,60 m -> 5 pav');
  afirma(r.lei.origem === 'lei',
         'pe-direito NAO conta como alteracao de parametro legal');
  G.ajusta({pe_direito_m: 5.00});
  r = G.analisaLote(lote);
  afirma(r.gabarito_legal === 3, 'ZC com pe-direito 5,00 m -> 3 pav');

  /* --- zona SEM Tabela 7: sem gabarito legal, so estudo de massa --- */
  const ZR = {type:'FeatureCollection', features:[{type:'Feature',
    properties:{sigla:'ZPA SAO PAULO'},
    geometry:{type:'Polygon', coordinates:[quad]}}]};
  G.set(ZR, VIAS, {'ZPA SAO PAULO':{sigla:'ZPA SAO PAULO'}}, lei);
  G.ajusta({});
  r = G.analisaLote(lote);
  afirma(r.lei === null, 'zona fora da Tabela 7: sem modelo legal');
  afirma(r.pavimentos === null, 'gabarito indeterminado — o app nao arbitra');
  afirma(r.gabarito_legal === null, 'nao existe gabarito legal a informar');

  // nem forcando parametro nenhum se cria um gabarito
  G.ajusta({altura_max_m: 12, atme_pct: 200, alml_pct: 35});
  r = G.analisaLote(lote);
  afirma(r.lei === null,
         'forcar Tabela 7 nao cria modelo legal em zona fora da lei');
  afirma(r.pavimentos === null, 'gabarito segue indeterminado');

  // mas o estudo de massa funciona: o usuario escolhe os pavimentos
  const sZ = G.simulaGabarito(r, 4);
  afirma(sZ.afastamentos !== null,
         'estudo de massa aplica os afastamentos da Tabela 8');
  afirma(!sZ.excede_atme && !sZ.limitado_por_to,
         'sem ATME/ALML nenhum teto de area e aplicado');
  afirma(sZ.bloqueios.length === 0,
         'sem altura definida nao ha bloqueio de altura');
  afirma(sZ.area_construida_m2 > 0, 'ha volume a estudar');

  // e o bloco 3D marca esses pavimentos como indeterminados, nao excedentes
  const blocos = G.blocoEnvelope(r, 4, true);
  afirma(blocos.length === 4, 'bloco de 4 pavimentos gerado');
  afirma(blocos.every(b => b.properties.tipo === 'indeterminado'),
         'pavimentos marcados como indeterminados (nao "excedente")');
}

// ---------------------------------------------------------------- 11
console.log('\n11. alivios de afastamento (Art. 111 II, Art. 115)');
{
  const lei = proc('lei.json');
  const O = [-44.06, -2.57];
  const KX = 111320 * Math.cos(O[1] * Math.PI / 180), KY = 110574;
  const P2 = ([x, y]) => [O[0] + x / KX, O[1] + y / KY];
  const quad = [[-500,-500],[500,-500],[500,500],[-500,500],[-500,-500]].map(P2);
  const VIAS = {type:'FeatureCollection', features:[{type:'Feature',
    properties:{nome:'Rua Teste', tipo_osm:'residential'},
    geometry:{type:'LineString', coordinates:[[-300,-6],[300,-6]].map(P2)}}]};
  // usamos ZEU: altura 60 m, permite passar de 15 m e acionar o podio
  const ZEU = {type:'FeatureCollection', features:[{type:'Feature',
    properties:{sigla:'ZEU'}, geometry:{type:'Polygon', coordinates:[quad]}}]};
  G.set(ZEU, VIAS, {ZEU:{sigla:'ZEU'}}, lei);

  perto(G.afastamentosAte15m(3.0).lateral_m, 3.0,
        0, 'afastamento de ate 15 m -> faixa 3a5 -> lateral 3,0');

  /* LOTE ESTREITO: 14 m de frente na ZEU (altura 60 m).
     Com os afastamentos da Tabela 8 lidos direto do autografo, o 6o
     pavimento exige 3,00 + 0,65 = 3,65 m de lateral, nao 7 m. Sobram
     14 - 7,3 = 6,7 m de largura, e o lote SOBE. So no 13o pavimento
     (lateral 7,40 m) a torre deixa de caber. */
  const estreito = [[0,0],[14,0],[14,40],[0,40]].map(P2);
  G.ajusta({}); G.opta({podio:false});
  const semPodio = G.analisaLote(estreito);
  G.opta({podio:true});
  const comPodio = G.analisaLote(estreito);

  console.log(`       lote 14x40 m — sem podio: ${semPodio.pavimentos} pav | `
            + `com podio: ${comPodio.pavimentos} pav | `
            + `maior area em ${comPodio.pavimentos_max_area} pav`);
  afirma(semPodio.pavimentos === 12,
         'lote de 14 m chega a 12 pavimentos (art. 111, nao 7 m fixos)');
  const trava13 = G.simulaGabarito(comPodio, 13);
  afirma(trava13.bloqueios.some(b => b.tipo === 'afastamento_torre'),
         'o 13o pavimento e bloqueado pela torre, e o app diz isso');

  /* REGRESSAO CRITICA: o gabarito mais alto NAO e o de maior area. Aqui a
     laje encolhe mais rapido do que os pavimentos se somam, e parar antes
     do teto rende muito mais. Chamar 12 pavimentos de "area construivel
     maxima" entregaria o pior projeto como se fosse o melhor. */
  afirma(comPodio.pavimentos_max_area < comPodio.pavimentos,
         'gabarito de maior area e MENOR que o gabarito maximo viavel');
  const sTopo = G.simulaGabarito(comPodio, comPodio.pavimentos);
  const sOtimo = G.simulaGabarito(comPodio, comPodio.pavimentos_max_area);
  afirma(sOtimo.area_construida_m2 > sTopo.area_construida_m2,
         'parar antes do teto legal rende mais area');
  perto(comPodio.area_construivel_m2, sOtimo.area_construida_m2, 1e-6,
        'area construivel = a do gabarito de maior area, nao a do mais alto');
  console.log(`       14x40 — ${comPodio.pavimentos} pav: `
            + `${sTopo.area_construida_m2.toFixed(0)} m2 | `
            + `${comPodio.pavimentos_max_area} pav: `
            + `${sOtimo.area_construida_m2.toFixed(0)} m2`);

  /* LOTE LARGO (20 m): a torre cabe folgada, e ai o podio mostra o seu
     valor — mais area nos cinco primeiros pavimentos. Usamos 6 pavimentos
     porque a partir do 8o a ATME de 360% ja trava os dois cenarios no mesmo
     teto, e a comparacao perderia o sentido. */
  const largo = [[0,0],[20,0],[20,40],[0,40]].map(P2);
  G.opta({podio:false});
  const l6sem = G.simulaGabarito(G.analisaLote(largo), 6);
  G.opta({podio:true});
  const rl = G.analisaLote(largo);
  const s6 = G.simulaGabarito(rl, 6);
  afirma(s6.usa_podio === true, '6 pav (18 m) aciona o podio');
  afirma(s6.n_podio === 5 && s6.n_torre === 1,
         'podio = 5 pavimentos, torre = o restante');
  afirma(s6.area_projecao_bruta_m2 > (s6.area_projecao_torre_m2 || 0),
         'projecao do podio maior que a da torre');
  afirma(!s6.excede_atme && !l6sem.excede_atme,
         'cenario escolhido nao esbarra na ATME (senao a comparacao empata)');
  afirma(s6.area_construida_m2 > l6sem.area_construida_m2,
         'podio aumenta a area construida quando a torre cabe');
  console.log(`       lote 20x40 m, 6 pav — sem podio: `
            + `${l6sem.area_construida_m2.toFixed(0)} m2 | com podio: `
            + `${s6.area_construida_m2.toFixed(0)} m2`);

  // abaixo de 15 m o podio nao se aplica
  const s4 = G.simulaGabarito(rl, 4);   // 12 m
  afirma(s4.usa_podio === false, '4 pav (12 m) nao aciona o podio');

  /* Art. 115 — EMPENA CEGA. O limite de 9 m e da OCUPACAO, nao do predio:
     "poderá ocupar um dos afastamentos laterais ... desde que não ultrapasse
     9,00m de altura". Logo um predio alto encosta na divisa ate essa cota e
     recua acima dela — a empena e decidida pavimento a pavimento. */
  const lote2 = [[0,0],[20,0],[20,40],[0,40]].map(P2);
  G.opta({podio:true, empenaCega:true});
  const r115 = G.analisaLote(lote2);
  const t3 = G.simulaGabarito(r115, 3);    //  9 m — cabe inteiro sob a cota
  const t4 = G.simulaGabarito(r115, 4);    // 12 m — o 4o pavimento ja nao
  afirma(t3.n_pav_empena === 3, '3 pav (9 m): os tres encostam na divisa');
  afirma(t4.n_pav_empena === 3,
         '4 pav (12 m): so os 3 primeiros encostam; o 4o recua');
  afirma(t4.pavimentos[3].empena === false,
         'o pavimento acima de 9 m volta a respeitar o afastamento');
  afirma(t4.pavimentos[3].projecao_bruta_m2 < t4.pavimentos[2].projecao_bruta_m2,
         'e por isso a projecao do 4o pavimento e menor que a do 3o');

  G.opta({podio:true, empenaCega:false});
  const t3sem = G.simulaGabarito(G.analisaLote(lote2), 3);
  afirma(t3.area_construida_m2 > t3sem.area_construida_m2,
         'a empena cega aumenta a area construida');
  console.log(`       3 pav — sem empena: `
            + `${t3sem.area_construida_m2.toFixed(0)} m2 | com: `
            + `${t3.area_construida_m2.toFixed(0)} m2 `
            + `(${t3.n_pav_empena} pav. na divisa)`);

  /* O lado da empena e escolha de projeto: o usuario fixa a divisa. Sem
     escolha, cai na maior lateral, que e a que mais rende. */
  const disp = G.lateraisDisponiveis(r115);
  afirma(disp.length >= 2, 'lote tem mais de uma lateral disponivel');
  afirma(disp[0].comprimento >= disp[1].comprimento,
         'as laterais vem ordenadas da maior para a menor');
  afirma(disp.every(l => l.rumo && typeof l.rumo === 'string'),
         'cada lateral traz um rumo, para o usuario achar o lado no mapa');
  G.opta({podio:true, empenaCega:true, ladoEmpena: disp[1].i});
  const rOutro = G.analisaLote(lote2);
  afirma(G.lateralDaEmpena(rOutro) === disp[1].i,
         'a divisa escolhida pelo usuario e respeitada');
  G.opta({podio:true, empenaCega:true, ladoEmpena: 999});
  afirma(G.lateralDaEmpena(G.analisaLote(lote2)) === disp[0].i,
         'lado inexistente (lote redesenhado) cai na maior lateral');
  // uma testada nunca pode virar empena: o afastamento frontal e inegociavel
  const frentes = new Set(r115.frentes.map(f => f.i));
  afirma(disp.every(l => !frentes.has(l.i)),
         'nenhuma testada aparece como divisa disponivel para a empena');
}

// ---------------------------------------------------------------- 11b
console.log('\n11b. area computavel x area construida (arts. 100, 101, 105)');
{
  const lei = proc('lei.json');
  const O = [-44.06, -2.57];
  const KX = 111320 * Math.cos(O[1] * Math.PI / 180), KY = 110574;
  const P2 = ([x, y]) => [O[0] + x / KX, O[1] + y / KY];
  const quad = [[-500,-500],[500,-500],[500,500],[-500,500],[-500,-500]].map(P2);
  const VIAS = {type:'FeatureCollection', features:[{type:'Feature',
    properties:{nome:'Rua Teste', tipo_osm:'residential'},
    geometry:{type:'LineString', coordinates:[[-300,-6],[300,-6]].map(P2)}}]};
  // ZC: ATME 240%, ALML 30% -> ocupacao 70%, altura 15 m
  const ZC = {type:'FeatureCollection', features:[{type:'Feature',
    properties:{sigla:'ZC'}, geometry:{type:'Polygon', coordinates:[quad]}}]};
  G.set(ZC, VIAS, {ZC:{sigla:'ZC'}}, lei);
  G.ajusta({});
  const lote = [[0,0],[40,0],[40,50],[0,50]].map(P2);   // 2.000 m2

  /* A ATME NAO varia com o gabarito: e percentual fixo da area do lote.
     Verificamos que o teto e o mesmo em 2 e em 5 pavimentos. */
  G.opta({});
  const r = G.analisaLote(lote);
  const atme = r.area_m2 * 2.40;
  for(const n of [2, 3, 5]){
    const s = G.simulaGabarito(r, n);
    perto(s.atme_max_m2, atme, 1,
          `ATME em ${n} pav e a mesma: 240% da area do lote`);
    afirma(s.area_computavel_m2 <= atme + 1e-6,
           `${n} pav: area computavel nunca ultrapassa a ATME`);
  }

  /* REGRESSAO CENTRAL: sem exclusao, construida == computavel e as duas
     param na ATME. Com exclusao, a construida PASSA da ATME — legalmente. */
  const base5 = G.simulaGabarito(r, 5);
  perto(base5.area_nao_computavel_m2, 0, 1e-9,
        'sem exclusoes nada fica fora da conta');
  perto(base5.area_construida_m2, base5.area_computavel_m2, 1e-9,
        'sem exclusoes, area construida == area computavel');
  perto(base5.area_computavel_m2, atme, 1, 'e as duas param na ATME');

  // Art. 101 — garagem
  G.opta({pavGaragem: 2});
  const rg = G.analisaLote(lote);
  const g5 = G.simulaGabarito(rg, 5);
  afirma(g5.n_garagem === 2, '2 pavimentos de garagem');
  afirma(g5.pavimentos.slice(0,2).every(p => p.tipo === 'garagem'
                                          && p.artigo === 'Art. 101'),
         'a garagem ocupa os pavimentos de baixo, citando o Art. 101');
  afirma(g5.pavimentos.slice(0,2).every(p => !p.computa),
         'pavimento de garagem nao computa na ATME');
  afirma(g5.area_nao_computavel_m2 > 0, 'a garagem sai da conta da ATME');
  afirma(g5.area_computavel_m2 <= atme + 1e-6,
         'a area computavel respeita a ATME');
  /* Trocar dois pavimentos-tipo por garagem REDUZ a area computavel (sobram
     3 pavimentos consumindo ATME em vez de 5) e AUMENTA a total. E o efeito
     que o art. 101 produz, e o painel precisa mostrar os dois numeros. */
  afirma(g5.area_computavel_m2 < base5.area_computavel_m2,
         'com garagem sobra menos area computavel');
  afirma(g5.area_construida_m2 > atme + 1,
         'RESPOSTA AO ART. 101: a area construida SUPERA a ATME');
  afirma(g5.area_construida_m2 > base5.area_construida_m2,
         'e supera tambem o cenario sem garagem');
  perto(g5.area_construida_m2,
        g5.area_computavel_m2 + g5.area_nao_computavel_m2, 1e-9,
        'total = computavel + nao computavel');
  console.log(`       ATME ${atme.toFixed(0)} m2 | 5 pav sem garagem: `
            + `${base5.area_construida_m2.toFixed(0)} m2 | com 2 pav de `
            + `garagem: ${g5.area_construida_m2.toFixed(0)} m2`);

  // Art. 105 — pilotis: nao computa na ATME, MAS computa na altura
  G.opta({pilotis: true});
  const rp = G.analisaLote(lote);
  const p5 = G.simulaGabarito(rp, 5);
  afirma(p5.pavimentos[0].tipo === 'pilotis'
         && p5.pavimentos[0].artigo === 'Art. 105',
         'o terreo vira pilotis');
  afirma(!p5.pavimentos[0].computa, 'pilotis nao computa na ATME');
  perto(p5.altura_m, 5 * G.PE, 1e-9,
        'REGRESSAO: o pilotis CONTA na altura — 5 pav continuam 5 pav');
  afirma(p5.area_construida_m2 > p5.area_computavel_m2,
         'com pilotis a construida supera a computavel');

  // Art. 100 — cobertura, no maximo 50% da laje
  G.opta({coberturaUnidades: true});
  const rc = G.analisaLote(lote);
  const c5 = G.simulaGabarito(rc, 5);
  const topo = c5.pavimentos[4];
  afirma(topo.tipo === 'cobertura' && topo.artigo === 'Art. 100',
         'o ultimo pavimento vira cobertura');
  perto(topo.area_m2, topo.projecao_m2 * 0.5, 1e-9,
        'a cobertura entra com 50% da laje, como manda o Art. 100');
  afirma(!topo.computa, 'a cobertura nao computa na ATME');

  /* As tres juntas, num predio de 8 pavimentos. Aqui a zona TEM de ser a ZEU
     (60 m): em ZC, 8 pavimentos passam dos 15 m e sairiam todos como
     'excedente' — o excesso de altura tem precedencia sobre a natureza do
     pavimento, e com razao. */
  const ZEU = {type:'FeatureCollection', features:[{type:'Feature',
    properties:{sigla:'ZEU'}, geometry:{type:'Polygon', coordinates:[quad]}}]};
  G.set(ZEU, VIAS, {ZEU:{sigla:'ZEU'}}, lei);
  G.opta({pilotis:true, pavGaragem:2, coberturaUnidades:true});
  const rt = G.analisaLote(lote);
  const atmeZeu = rt.area_m2 * 3.60;
  const t8 = G.simulaGabarito(rt, 8);
  const tipos = t8.pavimentos.map(p => p.tipo);
  afirma(tipos[0] === 'pilotis', 'ordem: pilotis no terreo');
  afirma(tipos[1] === 'garagem' && tipos[2] === 'garagem',
         'ordem: garagem logo acima');
  afirma(tipos[3] === 'computavel' && tipos[6] === 'computavel',
         'ordem: pavimentos-tipo no meio');
  afirma(tipos[7] === 'cobertura', 'ordem: cobertura no topo');
  afirma(t8.n_pav_computaveis === 4, '4 dos 8 pavimentos consomem ATME');
  afirma(t8.area_computavel_m2 <= atmeZeu + 1e-6,
         'mesmo com tudo ligado, a computavel respeita a ATME');
  afirma(t8.pavimentos.every(p => p.tipo !== 'excedente'),
         '8 pav (24 m) cabem na ZEU, entao nenhum e excedente');
  console.log(`       ZEU, 8 pav (pilotis + 2 garagens + cobertura): computavel `
            + `${t8.area_computavel_m2.toFixed(0)} m2 (ATME `
            + `${atmeZeu.toFixed(0)}) | total `
            + `${t8.area_construida_m2.toFixed(0)} m2`);

  // cores distintas por natureza do pavimento
  const cores = new Set(['computavel','garagem','pilotis','cobertura']
    .map(t => G.COR_PAV[t]));
  afirma(cores.size === 4, 'cada natureza de pavimento tem a sua cor');
  const bloco = G.blocoEnvelope(rt, 8, true);
  afirma(bloco[0].properties.tipo === 'pilotis'
         && bloco[1].properties.tipo === 'garagem'
         && bloco[7].properties.tipo === 'cobertura',
         'o bloco 3D carrega o tipo de cada pavimento para a cor');
  afirma(bloco.every(f => f.properties.artigo !== undefined),
         'cada pavimento leva o artigo que o classifica');

  /* REGRESSAO: o excesso de altura tem PRECEDENCIA sobre a natureza do
     pavimento. Uma garagem acima da altura maxima da zona e ilegal, e pintar
     de cinza esconderia isso — art. 101 condiciona a exclusao a "não
     ultrapassar a altura máxima permitida pela zona". */
  G.set(ZC, VIAS, {ZC:{sigla:'ZC'}}, lei);
  G.opta({pilotis:true, pavGaragem:2, coberturaUnidades:true});
  const rzc = G.analisaLote(lote);
  const b8zc = G.blocoEnvelope(rzc, 8, true);   // 24 m numa zona de 15 m
  afirma(b8zc.slice(5).every(f => f.properties.tipo === 'excedente'),
         'em ZC os pavimentos acima de 15 m saem como excedente, nao cinza');
  afirma(b8zc[0].properties.tipo === 'pilotis',
         'abaixo da altura maxima a natureza do pavimento continua valendo');

  /* A lei nao tem solo criado nem outorga: registrado no lei.json para o app
     nao sugerir um caminho de compra de potencial que nao existe. */
  afirma(lei.instrumentos_ausentes && lei.instrumentos_ausentes.solo_criado,
         'a ausencia de solo criado esta registrada');
  afirma(lei.instrumentos_ausentes.outorga_onerosa,
         'a ausencia de outorga onerosa esta registrada');
  afirma(lei.atme_varia_com_gabarito === false,
         'registrado que a ATME NAO varia com o gabarito');
  const modelaveis = lei.exclusoes_atme.filter(e => e.modelavel).map(e => e.chave);
  afirma(modelaveis.length === 3
         && ['cobertura','garagem','pilotis'].every(k => modelaveis.includes(k)),
         'as 3 exclusoes modelaveis sao cobertura, garagem e pilotis');
  afirma(lei.exclusoes_atme.filter(e => !e.modelavel).length === 3,
         'as outras 3 (arts. 102 a 104) ficam so no texto');
}

// ---------------------------------------------------------------- 11c
console.log('\n11c. a ALML entra na GEOMETRIA, nao so na conta');
{
  /* REGRESSAO DE UM DEFEITO REAL: o app truncava a taxa de ocupacao so no
     numero e continuava desenhando o bloco na projecao cheia. O painel dizia
     1.400 m2 e o mapa, o export GeoJSON e o laudo mostravam 1.566 m2 — 78,3%
     de um lote onde a lei permite 70%.

     Por isso estas assercoes medem a AREA DO ANEL, e nao o campo de area:
     era exatamente essa a diferenca que passava despercebida. */
  const lei = proc('lei.json');
  const O = [-44.06, -2.57];
  const KX = 111320 * Math.cos(O[1] * Math.PI / 180), KY = 110574;
  const P2 = ([x, y]) => [O[0] + x / KX, O[1] + y / KY];
  const quad = [[-500,-500],[500,-500],[500,500],[-500,500],[-500,-500]].map(P2);
  const VIAS = {type:'FeatureCollection', features:[{type:'Feature',
    properties:{nome:'Rua Teste', tipo_osm:'residential'},
    geometry:{type:'LineString', coordinates:[[-300,-6],[300,-6]].map(P2)}}]};
  const ZC = {type:'FeatureCollection', features:[{type:'Feature',
    properties:{sigla:'ZC'}, geometry:{type:'Polygon', coordinates:[quad]}}]};
  G.set(ZC, VIAS, {ZC:{sigla:'ZC'}}, lei);
  G.ajusta({}); G.opta({});

  // area de um anel lon/lat, medida de forma independente do codigo sob teste
  const areaAnel = anel => Math.abs(G.shoelace(
    anel.map(p => [(p[0]-O[0])*KX, (p[1]-O[1])*KY])));

  const lote = [[0,0],[40,0],[40,50],[0,50]].map(P2);   // 2.000 m2
  const r = G.analisaLote(lote);
  const toMax = r.area_m2 * 0.70;                        // ZC: ALML 30%

  /* REGRESSAO DO ENVELOPE DO TERREO. Ele aplicava SO o afastamento frontal:
     nem lateral, nem fundos, nem ALML. Era esse anel que ia para o mapa, para
     o GeoJSON e para o laudo — e o export ainda o multiplicava pelo numero de
     pavimentos. A projecao do terreo tem de obedecer aos DOIS limites ao
     mesmo tempo: os afastamentos da Tabela 8 e a ALML da Tabela 7. */
  const af1 = G.afastamentosPara(1);
  perto(areaAnel(r.envelope), r.area_envelope_m2, 1,
        'terreo: area declarada == area do anel');
  afirma(r.area_envelope_m2 <= toMax + 1e-6,
         'terreo: a projecao respeita a ALML');
  // so o frontal deixaria (50 - 5) x 40 = 1.800 m2; com lateral e fundos,
  // (50 - 5 - 1,5) x (40 - 2x1,5) = 43,5 x 37 = 1.609,5; com a ALML, 1.400
  const soFrontal = (50 - af1.frontal_m) * 40;
  afirma(r.area_envelope_m2 < soFrontal - 100,
         `terreo: nao e o recorte so do frontal (${soFrontal.toFixed(0)} m2)`);
  perto(r.area_envelope_afastamentos_m2,
        (50 - af1.frontal_m - af1.fundos_m) * (40 - 2*af1.lateral_m), 2,
        'terreo: lateral e fundos entram no recorte, nao so o frontal');
  afirma(r.envelope_limitado_por_alml === true,
         'terreo: o app sinaliza que a ALML mandou neste lote');
  perto(r.area_envelope_m2, toMax, 1,
        'terreo: a projecao para exatamente no teto da ALML');
  // e o envelope so do alinhamento continua disponivel, mas separado
  perto(r.area_alinhamento_m2, soFrontal, 2,
        'o recorte so do frontal fica como diagnostico de alinhamento');
  console.log(`       terreo: so frontal ${soFrontal.toFixed(0)} m2 -> `
            + `com lateral/fundos ${r.area_envelope_afastamentos_m2.toFixed(0)}`
            + ` m2 -> com ALML ${r.area_envelope_m2.toFixed(0)} m2`);

  const s = G.simulaGabarito(r, 2);

  afirma(s.area_projecao_bruta_m2 > toMax,
         'cenario valido: sem a ALML a projecao passaria de 70%');
  perto(areaAnel(s.envelope), toMax, 1,
        'o ANEL do envelope respeita a taxa de ocupacao');
  for(const p of s.pavimentos){
    perto(areaAnel(p.anel), toMax, 1,
          `pav ${p.i+1}: o ANEL respeita a taxa de ocupacao`);
    perto(areaAnel(p.anel), p.projecao_m2, 1,
          `pav ${p.i+1}: area declarada == area do anel desenhado`);
  }
  const bloco = G.blocoEnvelope(r, 2, true);
  for(const f of bloco)
    afirma(areaAnel(f.geometry.coordinates[0]) <= toMax + 1,
           `bloco 3D pav ${f.properties.pavimento}: nao ultrapassa a ocupacao`);
  perto(s.ocupacao_pct, 70, 0.1, 'ocupacao resultante = 70% do lote');
  afirma(s.limitado_por_to === true, 'o painel sinaliza o limite da ALML');
  afirma(s.recuo_alml_m > 0,
         'e informa quanto o bloco recuou alem do afastamento');
  console.log(`       lote ${r.area_m2.toFixed(0)} m2 | apos afastamentos `
            + `${s.area_projecao_bruta_m2.toFixed(0)} m2 | ALML corta para `
            + `${areaAnel(s.envelope).toFixed(0)} m2 `
            + `(recuo extra ${s.recuo_alml_m.toFixed(2)} m)`);

  // lote pequeno: os afastamentos ja deixam menos que a ocupacao maxima,
  // entao a ALML nao deve tirar nada nem deslocar a geometria
  const peq = [[0,0],[14,0],[14,25],[0,25]].map(P2);
  const rp = G.analisaLote(peq);
  const sp = G.simulaGabarito(rp, 1);
  if(sp.area_projecao_bruta_m2 < rp.area_m2 * 0.70){
    afirma(sp.limitado_por_to === false,
           'onde a projecao ja cabe, a ALML nao e acionada');
    perto(sp.recuo_alml_m, 0, 1e-9, 'e nao ha recuo adicional');
    perto(areaAnel(sp.envelope), sp.area_projecao_bruta_m2, 1,
          'a geometria fica intacta');
  }

  /* A ALML e a ATME sao limites DIFERENTES e independentes: a primeira
     limita a projecao (quanto do lote), a segunda a area total (quanto de
     laje). Um lote pode bater numa e nao na outra. */
  const s5 = G.simulaGabarito(r, 5);
  afirma(s5.area_projecao_m2 <= toMax + 1e-6,
         '5 pav: projecao continua dentro da taxa de ocupacao');
  afirma(s5.area_computavel_m2 <= r.area_m2 * 2.40 + 1e-6,
         '5 pav: area computavel continua dentro da ATME');
  afirma(s5.limites.some(x => x.tipo === 'ocupacao')
      && s5.limites.some(x => x.tipo === 'atme'),
         'os dois limites aparecem separados no painel');

  // zona sem Tabela 7: sem ALML nao ha teto de ocupacao a aplicar
  const ZPA = {type:'FeatureCollection', features:[{type:'Feature',
    properties:{sigla:'ZPA JENIPARANA'},
    geometry:{type:'Polygon', coordinates:[quad]}}]};
  G.set(ZPA, VIAS, {'ZPA JENIPARANA':{sigla:'ZPA JENIPARANA'}}, lei);
  const rz = G.analisaLote(lote);
  const sz = G.simulaGabarito(rz, 2);
  afirma(sz.limitado_por_to === false,
         'sem ALML na Tabela 7 nenhum teto de ocupacao e arbitrado');
  perto(sz.recuo_alml_m, 0, 1e-9, 'e a geometria nao e encolhida');
}

// ---------------------------------------------------------------- 11d
console.log('\n11d. ZDU - A e as hipoteses de dispensa da ALML');
{
  const lei = proc('lei.json');
  const O = [-44.20, -2.49];
  const KX = 111320 * Math.cos(O[1] * Math.PI / 180), KY = 110574;
  const P2 = ([x, y]) => [O[0] + x / KX, O[1] + y / KY];
  const quad = [[-800,-800],[800,-800],[800,800],[-800,800],[-800,-800]].map(P2);
  const VIAS = {type:'FeatureCollection', features:[{type:'Feature',
    properties:{nome:'Rua Teste', tipo_osm:'residential'},
    geometry:{type:'LineString', coordinates:[[-600,-6],[600,-6]].map(P2)}}]};
  const Z = {type:'FeatureCollection', features:[{type:'Feature',
    properties:{sigla:'ZDU - A'},
    geometry:{type:'Polygon', coordinates:[quad]}}]};
  G.set(Z, VIAS, {'ZDU - A':{sigla:'ZDU - A', familia:'urbana'}}, lei);
  const areaAnel = anel => Math.abs(G.shoelace(
    anel.map(p => [(p[0]-O[0])*KX, (p[1]-O[1])*KY])));
  const lote = [[0,0],[40,0],[40,50],[0,50]].map(P2);   // 2.000 m2

  /* A ZDU - A tem a ALML mais restritiva entre as urbanas: 40%, ou seja
     ocupacao maxima de 60%. Era nela que o envelope errado do terreo mais
     aparecia — chegava a 90% quando so o afastamento frontal era aplicado. */
  const z = G.leiDaZona('ZDU - A');
  perto(z.alml_pct, 40, 0, 'ZDU - A: ALML de 40%');
  perto(z.taxa_ocupacao_max_pct, 60, 0, 'ZDU - A: ocupacao maxima de 60%');

  G.ajusta({}); G.opta({});
  const r = G.analisaLote(lote);
  const toMax = r.area_m2 * 0.60;
  perto(areaAnel(r.envelope), toMax, 1,
        'ZDU - A: o ANEL do terreo para em 60% do lote');
  afirma(r.area_alinhamento_m2 / r.area_m2 > 0.85,
         'cenario valido: so o frontal daria mais de 85% de ocupacao');
  console.log(`       ZDU - A, lote 2.000 m2: so frontal `
            + `${(r.area_alinhamento_m2/r.area_m2*100).toFixed(1)}% -> `
            + `com afastamentos `
            + `${(r.area_envelope_afastamentos_m2/r.area_m2*100).toFixed(1)}% -> `
            + `com ALML ${(r.area_envelope_m2/r.area_m2*100).toFixed(1)}%`);

  // nenhum pavimento, em nenhum gabarito, pode furar os 60%
  let pior = 0;
  for(let n=1;n<=Math.min(r.pavimentos, 20);n++){
    const s = G.simulaGabarito(r, n);
    for(const p of s.pavimentos)
      if(p.anel) pior = Math.max(pior, areaAnel(p.anel) / r.area_m2 * 100);
  }
  afirma(pior <= 60 + 0.05,
         `ZDU - A: pior ocupacao em 20 gabaritos = ${pior.toFixed(2)}% (max 60%)`);

  /* --- Art. 117: reforma em lote de Regularizacao Fundiaria ---
     E a UNICA hipotese na lei que alcanca a ALML. Dispensa os indices
     urbanisticos, menos permeabilidade e altura maxima. */
  G.opta({regimeLote:'reg_fundiaria'});
  const rf = G.analisaLote(lote);
  afirma(rf.lei.taxa_ocupacao_max_pct === null,
         'Art. 117: a ALML fica dispensada');
  afirma(rf.lei.atme_pct === null, 'Art. 117: a ATME fica dispensada');
  afirma(rf.lei.area_min_m2 === null && rf.lei.testada_min_m === null,
         'Art. 117: as dimensoes minimas do lote ficam dispensadas');
  perto(rf.lei.altura_max_m, 90, 0,
        'Art. 117: a altura maxima da zona PERMANECE (excecao expressa)');
  afirma(rf.ok_area === null && rf.ok_testada === null,
         'Art. 117: nao ha conformidade de lote a aferir');
  const sf = G.simulaGabarito(rf, 2);
  afirma(sf.limitado_por_to === false,
         'Art. 117: nenhum teto de ocupacao e aplicado');
  perto(sf.recuo_alml_m, 0, 1e-9, 'Art. 117: a geometria nao e encolhida');
  afirma(areaAnel(rf.envelope) > toMax,
         'Art. 117: o envelope passa dos 60% — e legal nesta hipotese');
  afirma(sf.excede_atme === false, 'Art. 117: nao ha ATME a exceder');
  // mas os afastamentos continuam: leitura conservadora, declarada no painel
  afirma(sf.afastamentos !== null,
         'Art. 117: os afastamentos da Tabela 8 continuam aplicados');
  perto(areaAnel(rf.envelope), rf.area_envelope_afastamentos_m2, 1,
        'Art. 117: o envelope e exatamente o dos afastamentos');
  console.log(`       Art. 117: envelope vai de `
            + `${areaAnel(r.envelope).toFixed(0)} m2 (60%) para `
            + `${areaAnel(rf.envelope).toFixed(0)} m2 `
            + `(${(areaAnel(rf.envelope)/rf.area_m2*100).toFixed(1)}%)`);

  /* --- Art. 147: Interesse Social ---
     Remete a Tabela de Parcelamento do Solo, que so tem area e testada
     minimas. NAO alcanca a ALML — e o app nao pode fingir que alcanca. */
  G.opta({regimeLote:'interesse_social'});
  const ris = G.analisaLote(lote);
  perto(ris.lei.area_min_m2, 125, 0,
        'Art. 147: area minima cai para 125 m2 (Tabela de Parcelamento)');
  perto(ris.lei.testada_min_m, 5, 0, 'Art. 147: testada minima cai para 5,00 m');
  perto(ris.lei.taxa_ocupacao_max_pct, 60, 0,
        'Art. 147: a ALML da zona CONTINUA valendo');
  perto(ris.lei.atme_pct, 370, 0, 'Art. 147: a ATME da zona continua valendo');
  perto(areaAnel(ris.envelope), toMax, 1,
        'Art. 147: o envelope continua parando em 60%');

  // e o lei.json declara o erro de remissao do art. 147
  const ai = lei.alteracao_indices;
  afirma(ai && ai.regularizacao_fundiaria.atinge_alml === true,
         'lei.json: o art. 117 esta marcado como o que alcanca a ALML');
  afirma(ai.interesse_social.atinge_alml === false,
         'lei.json: o art. 147 esta marcado como o que NAO alcanca');
  afirma(ai.interesse_social.erro_de_remissao.length > 40,
         'lei.json: o erro de remissao do art. 147 esta registrado');
  afirma(ai.regularizacao_fundiaria.ambiguidade.length > 40,
         'lei.json: a ambiguidade sobre os afastamentos esta registrada');

  G.opta({});
}

// ---------------------------------------------------------------- 11e
console.log('\n11e. INVARIANTE: o bloco desenhado == os numeros declarados');
{
  /* Este e o teste que teria pego os dois defeitos de uma vez.
     Ambos tinham a mesma forma: o teto (ALML, depois ATME) era aplicado ao
     NUMERO e a geometria seguia cheia. O painel dizia 8.177 m2 e o bloco
     somava 16.342 m2 — o dobro do que a lei autoriza, desenhado no mapa.

     Em vez de conferir campo por campo, aqui MEDIMOS OS ANEIS e exigimos
     que fechem com o declarado, varrendo zonas, formatos, gabaritos e
     combinacoes de opcoes. Qualquer teto novo que alguem aplique so ao
     numero cai aqui. */
  const lei = proc('lei.json');
  const CENARIOS = [
    ['ZDU - A', [-44.20, -2.49]],
    ['ZC',      [-44.057, -2.559]],
    ['ZEU',     [-44.12, -2.53]],
    ['ZS',      [-44.063, -2.549]],
  ];
  const FORMAS = [
    [[0,0],[42.5,0],[42.5,52],[0,52]],            // 2.210 m2, o do relato
    [[0,0],[14,0],[14,40],[0,40]],                // estreito
    [[0,0],[60,0],[60,60],[0,60]],                // grande
    [[0,0],[30,0],[30,15],[15,15],[15,30],[0,30]],// L
  ];
  const COMBOS = [
    {}, {podio:false}, {empenaCega:true},
    {pilotis:true, pavGaragem:2, coberturaUnidades:true},
    {empenaCega:true, pilotis:true, pavGaragem:3},
  ];

  let casos = 0, piorSoma = 0, piorAtme = 0, piorTO = 0;
  for(const [sigla, O] of CENARIOS){
    const KX = 111320*Math.cos(O[1]*Math.PI/180), KY = 110574;
    const P2 = ([x,y]) => [O[0]+x/KX, O[1]+y/KY];
    const quad = [[-900,-900],[900,-900],[900,900],[-900,900],[-900,-900]].map(P2);
    const VIAS = {type:'FeatureCollection', features:[{type:'Feature',
      properties:{nome:'R', tipo_osm:'residential'},
      geometry:{type:'LineString', coordinates:[[-700,-6],[700,-6]].map(P2)}}]};
    const Z = {type:'FeatureCollection', features:[{type:'Feature',
      properties:{sigla}, geometry:{type:'Polygon', coordinates:[quad]}}]};
    G.set(Z, VIAS, {[sigla]:{sigla, familia:'urbana'}}, lei);
    const areaAnel = a => Math.abs(G.shoelace(
      a.map(p => [(p[0]-O[0])*KX, (p[1]-O[1])*KY])));
    const z = G.leiDaZona(sigla);

    for(const forma of FORMAS){
      for(const op of COMBOS){
        G.ajusta({}); G.opta(op);
        const r = G.analisaLote(forma.map(P2));
        if(!r || !r.lei || !r.pavimentos) continue;
        const toMax = r.area_m2 * z.taxa_ocupacao_max_pct / 100;
        const atme  = r.area_m2 * z.atme_pct / 100;

        for(const n of [1, 2, 5, 8, Math.min(r.pavimentos, 30)]){
          if(n < 1 || n > r.pavimentos) continue;
          const s = G.simulaGabarito(r, n);
          if(!s || !s.pavimentos) continue;
          casos++;

          // 1. cada pavimento: o anel desenhado e a area declarada batem
          for(const p of s.pavimentos){
            if(!p.anel) continue;
            const a = areaAnel(p.anel);
            piorSoma = Math.max(piorSoma, Math.abs(a - p.projecao_m2));
            perto(a, p.projecao_m2, 1,
                  `${sigla} ${n}pav ${JSON.stringify(op)}: pav ${p.i+1} anel == projecao`);
            // 2. nenhum pavimento fura a taxa de ocupacao
            piorTO = Math.max(piorTO, a / toMax);
            afirma(a <= toMax + 1,
                   `${sigla} ${n}pav: pav ${p.i+1} respeita a ALML`);
          }

          // 3. a soma do que e COMPUTAVEL, medida nos aneis, cabe na ATME
          const somaComp = s.pavimentos
            .filter(p => p.computa && p.anel)
            .reduce((acc,p) => acc + areaAnel(p.anel), 0);
          piorAtme = Math.max(piorAtme, somaComp / atme);
          afirma(somaComp <= atme + 1,
                 `${sigla} ${n}pav ${JSON.stringify(op)}: a SOMA DOS ANEIS `
                 + `computaveis (${somaComp.toFixed(0)}) cabe na ATME `
                 + `(${atme.toFixed(0)})`);
          perto(somaComp, s.area_computavel_m2, 1,
                `${sigla} ${n}pav: soma dos aneis == area computavel declarada`);

          // 4. o bloco 3D leva exatamente essa geometria
          const bloco = G.blocoEnvelope(r, n, true);
          const somaBloco = bloco
            .filter((f,i) => s.pavimentos[i] && s.pavimentos[i].computa)
            .reduce((acc,f) => acc + areaAnel(f.geometry.coordinates[0]), 0);
          perto(somaBloco, somaComp, 1,
                `${sigla} ${n}pav: o bloco 3D desenha a mesma area`);

          // 5. e o total declarado fecha com a soma de tudo que foi desenhado
          const somaTudo = s.pavimentos
            .filter(p => p.anel)
            .reduce((acc,p) => acc + areaAnel(p.anel) * p.fator, 0);
          perto(somaTudo, s.area_construida_m2, 1,
                `${sigla} ${n}pav: area construida == soma do que se desenhou`);

          /* 6. ENCAIXE: nenhum pavimento pode extrapolar o de baixo — a laje
             precisa de apoio. Os afastamentos so crescem com a altura, mas os
             tetos de area quebravam o encaixe: erodir aneis de formatos
             diferentes ate a MESMA area da formatos diferentes, e a torre
             chegava a avancar 0,74 m alem do podio, em direcao a rua. */
          for(let k=1;k<s.pavimentos.length;k++){
            const a = s.pavimentos[k], b = s.pavimentos[k-1];
            if(!a.anel || !b.anel) continue;
            /* "a esta contido em b" medido pela AREA DA INTERSECAO, nao por
               ponto-em-poligono: quando os dois pavimentos tem o mesmo anel,
               todo vertice cai exatamente sobre a borda e o teste de raio
               responde ora dentro, ora fora. */
            const dentro = G.intersectaAnel(a.anel, b.anel);
            perto(dentro.length >= 4 ? areaAnel(dentro) : 0, areaAnel(a.anel),
                  0.5, `${sigla} ${n}pav ${JSON.stringify(op)}: pav ${k+1} `
                     + `cabe inteiro dentro do pav ${k}`);
            afirma(areaAnel(a.anel) <= areaAnel(b.anel) + 0.5,
                   `${sigla} ${n}pav: pav ${k+1} nao e maior que o pav ${k}`);
          }

          /* 7. PILOTIS segue o pavimento de cima (Art. 105). E o terreo aberto
             do MESMO predio: os pilares ficam sob as lajes. Desenha-lo no
             maximo que a ALML permite deixava a torre recuada ~1,1 m em cada
             lado sobre uma base mais larga. */
          const pil = s.pavimentos.find(p => p.tipo === 'pilotis');
          if(pil && s.pavimentos[pil.i + 1] && pil.anel){
            const acima = s.pavimentos[pil.i + 1];
            perto(areaAnel(pil.anel), areaAnel(acima.anel), 0.5,
                  `${sigla} ${n}pav: pilotis tem a projecao do pavimento acima`);
            afirma(pil.segue_pavimento_acima === true,
                   `${sigla} ${n}pav: o pilotis declara que segue o de cima`);
          }
        }
      }
    }
  }
  console.log(`       ${casos} cenarios (4 zonas x 4 formatos x 5 combinacoes)`);
  console.log(`       maior desvio anel-vs-declarado: ${piorSoma.toFixed(4)} m2`);
  console.log(`       maior uso da ATME: ${(piorAtme*100).toFixed(2)}% | `
            + `maior uso da ocupacao: ${(piorTO*100).toFixed(2)}%`);
  afirma(casos > 100, 'a varredura cobriu um numero significativo de cenarios');
  G.opta({});
}

// ---------------------------------------------------------------- 12
console.log('\n12. o mapa novo confere com as tabelas de parametros');
{
  const lei = proc('lei.json');
  const zon = proc('zoneamento.geojson');
  const par = proc('parametros.json');
  const qa  = proc('zonas_qa.json');

  /* A Tabela 1 da lei lista 12 zonas; os memoriais descrevem essas 12 mais
     o Parque da Quinta, que fica dentro da ZPA Jeniparana. */
  afirma(zon.features.length === 13,
         `13 zonas com memorial descritivo (achei ${zon.features.length})`);
  afirma(Object.keys(lei.zonas).length === 10,
         'a Tabela 7 do autografo traz 10 zonas, nao 11');
  afirma(!('ZAAJ' in lei.zonas),
         'ZAAJ nao consta da lei sancionada e nao esta no lei.json');

  /* Cobertura nos dois sentidos — e este o cruzamento que importa:
     toda zona da Tabela 7 tem geometria, e toda geometria sem parametro
     esta declarada como tal, nunca preenchida por semelhanca. */
  const cob = lei.cobertura;
  afirma(cob.zonas_com_parametro_sem_geometria.length === 0,
         'nenhuma zona da Tabela 7 ficou sem memorial descritivo');
  afirma(cob.zonas_com_geometria_e_parametro.length === 10,
         '10 zonas tem geometria e parametro');
  afirma(cob.zonas_com_geometria_sem_parametro.length === 3,
         'as 3 ambientais tem geometria e nenhum parametro');
  for(const s of cob.zonas_com_geometria_sem_parametro)
    afirma(lei.zonas_sem_parametro[s],
           `${s}: ausencia de parametro declarada explicitamente`);

  // cada feicao carrega os mesmos numeros que a Tabela 7 transcrita
  for(const f of zon.features){
    const p = f.properties, z = lei.zonas[p.sigla];
    if(!z){
      afirma(p.atme_pct == null && p.alml_pct == null && p.altura_max_m == null,
             `${p.sigla}: sem parametro na geometria, como na Tabela 7`);
      continue;
    }
    perto(p.atme_pct,     z.atme_pct,     0, `${p.sigla}: ATME bate com a Tabela 7`);
    perto(p.alml_pct,     z.alml_pct,     0, `${p.sigla}: ALML bate com a Tabela 7`);
    perto(p.altura_max_m, z.altura_max_m, 0, `${p.sigla}: altura bate com a Tabela 7`);
    perto(p.area_min_m2,  z.area_min_m2,  0, `${p.sigla}: lote minimo bate`);
    perto(p.testada_min_m, z.testada_min_m, 0, `${p.sigla}: testada minima bate`);
    perto(p.taxa_ocupacao_max_pct, 100 - z.alml_pct, 0,
          `${p.sigla}: taxa de ocupacao = 100 - ALML`);
  }

  /* Sanidade da conversao UTM -> WGS84: shoelace no plano UTM e na esfera
     tem de dar praticamente a mesma area. Divergencia grande significaria
     projecao errada, e o poligono estaria deslocado no mapa. */
  const piorConv = Math.max(...qa.zonas.map(z => z.divergencia_pct));
  afirma(piorConv < 0.5,
         `area UTM vs WGS84: pior divergencia ${piorConv.toFixed(4)}% (< 0,5%)`);

  // todo poligono cai dentro do municipio
  for(const f of zon.features){
    const anel = f.geometry.coordinates[0];
    const fora = anel.filter(p => p[0] < -44.40 || p[0] > -43.90
                               || p[1] < -2.90  || p[1] > -2.30);
    afirma(fora.length === 0,
           `${f.properties.sigla}: todos os vertices na area do municipio`);
  }

  // anel fechado e orientado como manda o RFC 7946 (exterior anti-horario)
  for(const f of zon.features){
    const anel = f.geometry.coordinates[0];
    afirma(anel[0][0] === anel[anel.length-1][0]
        && anel[0][1] === anel[anel.length-1][1],
           `${f.properties.sigla}: anel fechado`);
    afirma(G.shoelace(anel.map(([x,y]) => [x,y])) > 0,
           `${f.properties.sigla}: anel exterior anti-horario`);
  }

  console.log(`       ${zon.features.length} zonas | `
            + `${(Object.values(par).reduce((a,z)=>a+z.area_m2,0)/1e6).toFixed(1)} km2 | `
            + `pior divergencia de projecao ${piorConv.toFixed(4)}%`);
}

// ---------------------------------------------------------------- 13
console.log('\n13. geometria e parametros saem do mesmo documento');
{
  const lei = proc('lei.json');
  const zon = proc('zoneamento.geojson');

  // a lei traz as instrucoes gerais, com artigo citado
  const regras = lei.regras || {};
  for(const k of ['taxa_permeabilidade_pct','pe_direito_min_m',
                  'pavimentos_livres','afastamento_frontal_por_testada',
                  'altura_pela_maior_testada']){
    afirma(regras[k] && regras[k].artigo && regras[k].texto,
           `regra "${k}" tem artigo e texto para exibir`);
  }
  perto(regras.taxa_permeabilidade_pct.valor, 20, 0,
        'permeabilidade 20% (Art. 98) vale em todas as zonas');
  afirma(lei.afastamentos_por_gabarito.length === 6,
         'Tabela 8 completa disponivel para exibicao (6 faixas)');
  // as faixas acima de 5 pavimentos vem marcadas como nao tabeladas, para o
  // painel poder mostrar intervalo em vez de um numero unico
  const naoTab = lei.afastamentos_por_gabarito.filter(f => !f.tabelado);
  afirma(naoTab.length === 3,
         'as 3 faixas acima de 5 pavimentos estao marcadas como calculadas');
  afirma(naoTab.every(f => f.lateral_m_min !== f.lateral_m_max),
         'nessas faixas o afastamento varia dentro da propria faixa');
  afirma((lei.afastamentos_ressalvas || []).length >= 3,
         'as ambiguidades do art. 111 estao registradas para exibicao');

  // toda zona do mapa recebe uma tabela de usos indicada
  const semTabela = zon.features
    .map(f => f.properties.sigla)
    .filter(s => !(lei.usos.por_zona || {})[s]);
  afirma(semTabela.length === 0,
         `todas as 13 zonas tem tabela de usos indicada `
         + `(sem indicacao: ${semTabela.join(', ') || 'nenhuma'})`);
  afirma(lei.usos.tabelas['6.1'].zonas.includes('ZRG'),
         'Tabela 6.1 nomeia as zonas rurais da lei');
  afirma(lei.usos.tabelas['6.3'].zonas.includes('ZC'),
         'Tabela 6.3 nomeia as zonas urbanas da lei');
  afirma(lei.usos.tabelas['6.2'].zonas.includes('ZPA JENIPARANA'),
         'Tabela 6.2 nomeia as zonas de preservacao');

  const semArea = zon.features.filter(f => !(f.properties.area_m2 > 0));
  afirma(semArea.length === 0, 'toda zona tem area medida no poligono');
  const semFonte = zon.features.filter(f => !f.properties.fonte);
  afirma(semFonte.length === 0, 'toda zona declara a origem da geometria');

  /* REGRESSAO: o KMZ foi descartado. Nenhum campo dele pode voltar a
     alimentar o painel de consulta — conferimos no proprio index.html.
     renderConsulta vai ate a declaracao de GRUPOS (secao de camadas). */
  const painel = fatia('function renderConsulta()', 'const GRUPOS = [');
  for(const campo of ['p.gabarito_max_pav', 'p.afastamento_frontal_m',
                      'correspondencia_kmz', 'por_zona_kmz']){
    afirma(painel.split(campo).length - 1 === 0,
           `${campo} nao aparece mais no painel de consulta`);
  }
  afirma(painel.includes('leiDaZona('),
         'a consulta busca os parametros na lei');
  afirma(painel.includes('Memorial descritivo'),
         'o painel declara que a geometria vem do memorial da lei');
}

console.log('\n' + (falhas ? `${falhas} FALHA(S)` : 'todos os testes passaram'));
process.exit(falhas ? 1 : 0);

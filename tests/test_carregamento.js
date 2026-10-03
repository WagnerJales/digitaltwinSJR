/* =====================================================================
   Testes do CARREGAMENTO DE DADOS do web/index.html.

       node tests/test_carregamento.js

   Por que existe: um `.catch()` preso ao `.json()` em vez do `fetch()`
   derrubava o handler de 'load' inteiro quando um arquivo faltava — e o
   resultado era um mapa em branco, com o erro só no console. O sintoma
   ("erro de API pra puxar o mapa") não apontava para a causa.

   Aqui exercitamos a função carrega() contra os quatro modos de falha
   reais: fetch que rejeita (file://), 404, JSON inválido e arquivo ausente.
   ===================================================================== */
const fs = require('fs');
const path = require('path');

const html = fs.readFileSync(
  path.join(__dirname, '..', 'web', 'index.html'), 'utf8');

let falhas = 0;
function afirma(ok, msg){
  console.log((ok ? '  ok   ' : ' FALHA ') + msg);
  if(!ok) falhas++;
}

function fatia(ini, fim){
  const a = html.indexOf(ini), b = html.indexOf(fim, a);
  if(a < 0 || b < 0){
    console.error(`ERRO: nao achei "${ini.slice(0,40)}" em index.html.`);
    process.exit(1);
  }
  return html.slice(a, b);
}

const bloco = fatia('const FALHAS = [];', "map.on('load'");

/** Monta um ambiente com DATA e um fetch controlado. */
function ambiente(fetchFake, embed){
  return new Function('fetch', 'window', `
    const DATA = {a:'/a.json', b:'/b.json'};
    ${bloco}
    return {carrega, FALHAS};
  `)(fetchFake, {__EMBED: embed});
}

const resp = (ok, status, corpo) => ({
  ok, status,
  json: async () => {
    if(typeof corpo === 'string') return JSON.parse(corpo);   // pode lancar
    return corpo;
  },
});

(async () => {
  console.log('\n1. dado embutido tem prioridade e nao toca a rede');
  {
    let chamou = false;
    const G = ambiente(async () => { chamou = true; return resp(true,200,{}); },
                       {a:{marca:'embutido'}});
    const r = await G.carrega('a');
    afirma(r && r.marca === 'embutido', 'devolve o embutido');
    afirma(chamou === false, 'nao chama fetch quando ha embutido');
    afirma(G.FALHAS.length === 0, 'nao registra falha');
  }

  console.log('\n2. fetch REJEITA (é o caso do file://, duplo clique)');
  {
    const G = ambiente(async () => { throw new TypeError('Failed to fetch'); });
    let r, explodiu = false;
    try { r = await G.carrega('a', {essencial:true, padrao:{vazio:true}}); }
    catch(e){ explodiu = true; }
    afirma(!explodiu,
      'REGRESSAO: nao propaga a excecao — era isto que matava o mapa inteiro');
    afirma(r && r.vazio === true, 'devolve o padrao informado');
    afirma(G.FALHAS.length === 1 && G.FALHAS[0].essencial === true,
      'registra a falha como essencial');
    afirma(/Failed to fetch/.test(G.FALHAS[0].erro),
      'guarda a mensagem original para o aviso na tela');
  }

  console.log('\n3. HTTP 404 — o fetch resolve, mas o arquivo nao existe');
  {
    const G = ambiente(async () => resp(false, 404, '<html>nao achei</html>'));
    const r = await G.carrega('a');
    afirma(r === null, 'devolve null');
    afirma(G.FALHAS.length === 1 && /404/.test(G.FALHAS[0].erro),
      'identifica o 404 pelo status, sem esperar o .json() estourar');
  }

  console.log('\n4. resposta 200 com JSON invalido');
  {
    const G = ambiente(async () => resp(true, 200, 'isto nao e json'));
    let explodiu = false;
    let r;
    try { r = await G.carrega('a'); } catch(e){ explodiu = true; }
    afirma(!explodiu, 'nao propaga o erro de parse');
    afirma(r === null && G.FALHAS.length === 1, 'registra a falha');
  }

  console.log('\n5. varias falhas somam, e a essencial fica marcada');
  {
    const G = ambiente(async () => { throw new TypeError('offline'); });
    await G.carrega('a', {essencial:true});
    await G.carrega('b');
    afirma(G.FALHAS.length === 2, 'duas falhas registradas');
    afirma(G.FALHAS.filter(f => f.essencial).length === 1,
      'apenas uma marcada como essencial');
    afirma(G.FALHAS.map(f => f.nome).join(',') === 'a,b',
      'preserva o nome de cada conjunto');
  }

  console.log('\n6. os nomes usados em DATA existem de fato');
  {
    const dataBloco = fatia('const DATA = {', '};');
    const nomes = [...dataBloco.matchAll(/^\s*([a-z_]+):/gm)].map(m => m[1]);
    const usados = [...html.matchAll(/carrega\('([a-z_]+)'/g)].map(m => m[1]);
    const orfas = [...new Set(usados)].filter(n => !nomes.includes(n));
    afirma(orfas.length === 0,
      `todo carrega() aponta para uma chave de DATA (orfas: ${orfas.join(', ') || 'nenhuma'})`);
    afirma(usados.length >= 5,
      `${usados.length} conjuntos carregados pelo helper`);
  }

  console.log('\n7. basemaps: nenhum exige chave, e ha reserva');
  {
    const bloco = html.slice(html.indexOf('// BASEMAPS raster sem chave'),
                             html.indexOf('const map = new maplibregl.Map'));
    const urls = [...bloco.matchAll(/'(https:[^']+)'/g)].map(m => m[1]);
    afirma(urls.length >= 3, `${urls.length} URLs de tile declaradas`);
    afirma(!/cartocdn/.test(bloco),
      'a CARTO saiu: passou a exigir API key e devolvia tile 200 com o aviso');
    const comChave = urls.filter(u => /[?&](api_?key|access_?token|key)=/i.test(u));
    afirma(comChave.length === 0,
      `nenhuma URL de tile carrega chave (achei: ${comChave.join(', ') || 'nenhuma'})`);
    afirma(/BASE_RESERVA/.test(bloco), 'existe basemap de reserva declarado');
    for(const nome of ['BASE_CLARO','BASE_SAT','BASE_RESERVA']){
      const j = bloco.indexOf('const ' + nome);
      const trecho = j < 0 ? '' : bloco.slice(j, j + 420);
      afirma(/attribution:/.test(trecho), nome + ' declara attribution');
    }
    afirma(html.includes("map.on('error'") && html.includes('usandoReserva'),
      'ha vigia que troca para a reserva quando os tiles falham');
  }

  console.log('\n' + (falhas ? `${falhas} FALHA(S)` : 'todos os testes passaram'));
  process.exit(falhas ? 1 : 0);
})();

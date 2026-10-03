/* =====================================================================
   Teste de PARTIDA do aplicativo (web/index.html).

       node tests/test_app.js

   Executa o script inteiro do index.html contra stubs mínimos de DOM e de
   MapLibre, dispara o evento 'load' e confere que as camadas e as fontes
   foram realmente criadas — nos DOIS modos de operação:

     servido    (fetch de data/processados, como `python -m http.server`)
     standalone (window.__EMBED, como dist/SJR-Geo.html)

   Por que existe: os testes de geometria cobrem o motor de cálculo, mas
   ninguém exercitava a partida. Foi ali que quebrou duas vezes seguidas —
   um `.catch()` preso ao `.json()` em vez do `fetch()`, e depois um
   `expandeEnderecos(SRC(...))` recebendo a URL em vez do dado no modo
   servido. Nos dois casos o handler de 'load' morria inteiro: mapa base na
   tela, nenhuma camada, e o erro só no console.
   ===================================================================== */
const fs = require('fs');
const path = require('path');

const RAIZ = path.join(__dirname, '..');
const PROC = path.join(RAIZ, 'data', 'processados');
const html = fs.readFileSync(path.join(RAIZ, 'web', 'index.html'), 'utf8');
const script = html.match(
  /<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/)[1];

let falhas = 0;
const afirma = (ok, msg) => {
  console.log((ok ? '  ok   ' : ' FALHA ') + msg);
  if (!ok) falhas++;
};

// ---------------------------------------------------------------- stubs
function elFalso(tag) {
  const e = {
    tagName: tag, style: { cssText: '' }, dataset: {}, children: [],
    textContent: '', innerHTML: '', value: '', type: '', checked: false,
    classList: {
      add() {}, remove() {}, contains() { return false; }, toggle() {},
    },
    appendChild(c) { this.children.push(c); return c; },
    insertBefore(c) { this.children.push(c); return c; },
    removeChild() {}, remove() {}, setAttribute() {}, removeAttribute() {},
    addEventListener() {}, removeEventListener() {},
    querySelector() { return null; }, querySelectorAll() { return []; },
    getBoundingClientRect() {
      return { width: 1200, height: 800, top: 0, left: 0 };
    },
    focus() {}, blur() {}, click() {},
  };
  Object.defineProperty(e, 'firstChild',
    { get() { return this.children[0] || null; } });
  Object.defineProperty(e, 'lastChild',
    { get() { return this.children[this.children.length - 1] || null; } });
  return e;
}

function documentoFalso() {
  const porId = new Map();
  return {
    createElement: (t) => elFalso(t),
    createTextNode: (t) => ({ nodeValue: t, textContent: t }),
    getElementById(id) {
      if (!porId.has(id)) porId.set(id, elFalso('div'));
      return porId.get(id);
    },
    querySelectorAll() { return []; },
    querySelector() { return null; },
    addEventListener() {},
    body: elFalso('body'),
  };
}

/** MapLibre mínimo: registra o que foi criado, para podermos conferir. */
function mapaFalso() {
  const fontes = new Map(), camadas = new Map(), handlers = {};
  return {
    fontes, camadas, handlers,
    on(ev, a, b) { (handlers[ev] = handlers[ev] || []).push(b || a); },
    off() {}, once() {},
    addSource(id, src) {
      fontes.set(id, Object.assign({}, src, { setData() {}, setTiles() {} }));
    },
    getSource(id) { return fontes.get(id); },
    addLayer(l) { camadas.set(l.id, l); },
    getLayer(id) { return camadas.get(id); },
    removeLayer(id) { camadas.delete(id); },
    setLayoutProperty(id, k, v) {
      const c = camadas.get(id);
      // deixar isto passar em silêncio esconderia camada fantasma em GRUPOS
      if (!c) throw new Error('setLayoutProperty em camada inexistente: ' + id);
      c.layout = Object.assign({}, c.layout || {}, { [k]: v });
    },
    getLayoutProperty(id, k) {
      const c = camadas.get(id);
      return c && c.layout ? c.layout[k] : undefined;
    },
    setPaintProperty() {}, setFilter() {}, setFeatureState() {},
    addControl() {}, removeControl() {},
    getCanvas() { return { style: {} }; },
    getContainer() { return elFalso('div'); },
    getZoom() { return 11; }, getBearing() { return 0; }, getPitch() { return 0; },
    getCenter() { return { lng: -44.05, lat: -2.55 }; },
    fitBounds() {}, jumpTo() {}, easeTo() {}, flyTo() {}, zoomIn() {}, zoomOut() {},
    isStyleLoaded() { return true; }, triggerRepaint() {}, resize() {},
    doubleClickZoom: { enable() {}, disable() {} },
    dragRotate: { enable() {}, disable() {} },
    style: { sourceCaches: {} },
  };
}

/** fetch que lê data/processados do disco, como o servidor HTTP faria. */
async function fetchDisco(url) {
  const arq = path.join(PROC, path.basename(String(url)));
  if (!fs.existsSync(arq)) {
    return { ok: false, status: 404, async json() { throw new Error('404'); } };
  }
  const txt = fs.readFileSync(arq, 'utf8');
  return { ok: true, status: 200, async json() { return JSON.parse(txt); } };
}

/** Sobe o app e devolve o mapa depois de o 'load' terminar. */
async function sobeApp(opt) {
  const embed = (opt && opt.embed) || null;
  const protocolo = (opt && opt.protocolo) || 'http:';
  const doc = documentoFalso();
  const mapa = mapaFalso();
  const win = {
    __EMBED: embed, addEventListener() {},
    matchMedia: () => ({ matches: false }),
  };
  const maplibregl = {
    Map: function () { return mapa; },
    NavigationControl: function () {}, ScaleControl: function () {},
  };
  const loc = { protocol: protocolo, hash: '',
    href: protocolo === 'file:'
      ? 'file:///C:/SJR/dist/SJR-Geo.html'
      : 'http://localhost:8080/web/' };
  // em file:// o navegador BLOQUEIA fetch — nem chega ao servidor
  const fetchUsado = protocolo === 'file:'
    ? async () => { throw new TypeError('Failed to fetch'); }
    : fetchDisco;
  const fn = new Function(
    'maplibregl', 'document', 'window', 'location', 'history', 'fetch',
    'console', 'setTimeout', 'navigator', 'alert', 'URLSearchParams',
    'Blob', 'URL',
    script + '\n;return {mapa: map, FALHAS: FALHAS};');
  const r = fn(
    maplibregl, doc, win, loc,
    { replaceState() {}, pushState() {} }, fetchUsado,
    { log() {}, warn() {}, error() {} }, setTimeout,
    { userAgent: 'node', clipboard: { writeText: async () => {} } },
    () => {}, URLSearchParams,
    function () {}, { createObjectURL: () => 'blob:', revokeObjectURL() {} });
  for (const h of (mapa.handlers.load || [])) await h();
  return { mapa: mapa, FALHAS: r.FALHAS };
}

// ---------------------------------------------------------------- testes
const CAMADAS = [
  'zoneamento-fill', 'zoneamento-line', 'gabarito-3d', 'setores-fill',
  'setores-line', 'vias-line', 'edif-3d', 'recorte-edif-line',
  'enderecos-heat', 'enderecos-pt', 'envelope-3d', 'lote-fill', 'lote-line',
  // loteamento
  'parcelas-fill', 'parcelas-line', 'quadras-line', 'parcelas-3d',
  'gleba-fill', 'gleba-line', 'gleba-pts',
];
const FONTES = ['zoneamento', 'edificacoes', 'vias', 'enderecos', 'setores',
  'lote', 'envelope', 'measure', 'gleba', 'parcelas'];

(async () => {
  console.log('\n1. modo SERVIDO (fetch de data/processados)');
  {
    const r = await sobeApp();
    afirma(r.FALHAS.length === 0,
      'nenhuma falha de carregamento ('
      + (r.FALHAS.map((f) => f.nome).join(', ') || '—') + ')');
    for (const id of FONTES) afirma(r.mapa.fontes.has(id), `fonte '${id}' criada`);
    for (const id of CAMADAS) afirma(r.mapa.camadas.has(id), `camada '${id}' criada`);

    const end = r.mapa.fontes.get('enderecos');
    afirma(!!(end && end.data && Array.isArray(end.data.features)),
      'REGRESSAO: a fonte de endereços recebeu DADO, não a URL');
    const n = (end && end.data && end.data.features.length) || 0;
    afirma(n > 100000, n.toLocaleString('pt-BR') + ' endereços expandidos');
    const p0 = end && end.data && end.data.features[0];
    afirma(!!(p0 && p0.geometry.type === 'Point' && p0.properties.zona),
      'cada endereço saiu como Point com zona');
  }

  console.log('\n2. modo STANDALONE (window.__EMBED)');
  {
    const embed = {};
    const arqs = {
      zoneamento: 'zoneamento.geojson', edificacoes: 'edificacoes.geojson',
      vias: 'vias.geojson', enderecos: 'enderecos.json',
      setores: 'setores.geojson', parametros: 'parametros.json',
      lei: 'lei.json', stats_edificacoes: 'stats_edificacoes.json',
    };
    for (const k of Object.keys(arqs)) {
      const f = path.join(PROC, arqs[k]);
      if (fs.existsSync(f)) embed[k] = JSON.parse(fs.readFileSync(f, 'utf8'));
    }
    const r = await sobeApp({ embed: embed });
    afirma(r.FALHAS.length === 0, 'nenhuma falha de carregamento');
    for (const id of CAMADAS) afirma(r.mapa.camadas.has(id), `camada '${id}' criada`);
    const end = r.mapa.fontes.get('enderecos');
    afirma(!!(end && end.data.features.length > 100000),
      'endereços expandidos também no standalone');
  }

  console.log('\n3. STANDALONE por duplo clique (file://, sem rede)');
  {
    /* É o caso real de quem recebe o arquivo por e-mail: protocolo file:// e
       fetch bloqueado pelo navegador. Tem de funcionar SEM nenhum fetch — se
       algum conjunto escapar do __EMBED, o aviso "precisa de um servidor"
       aparece indevidamente e o mapa fica sem camada nenhuma.

       Foi exatamente o que o usuário viu: abriu web/index.html por duplo
       clique (que NÃO tem dados embutidos) em vez de dist/SJR-Geo.html. */
    const embed = {};
    const arqs = {
      zoneamento: 'zoneamento.geojson', edificacoes: 'edificacoes.geojson',
      vias: 'vias.geojson', enderecos: 'enderecos.json',
      setores: 'setores.geojson', parametros: 'parametros.json',
      lei: 'lei.json', stats_edificacoes: 'stats_edificacoes.json',
    };
    for (const k of Object.keys(arqs)) {
      const f = path.join(PROC, arqs[k]);
      if (fs.existsSync(f)) embed[k] = JSON.parse(fs.readFileSync(f, 'utf8'));
    }
    const r = await sobeApp({ embed: embed, protocolo: 'file:' });
    afirma(r.FALHAS.length === 0,
      'em file:// com __EMBED, nenhum fetch e tentado ('
      + (r.FALHAS.map((f) => f.nome).join(', ') || 'zero falhas') + ')');
    for (const id of CAMADAS) afirma(r.mapa.camadas.has(id), `camada '${id}' criada`);
    const end = r.mapa.fontes.get('enderecos');
    afirma(!!(end && end.data.features.length > 100000),
      'enderecos expandidos sem tocar a rede');
  }

  console.log('\n4. dados AUSENTES: degrada, não morre');
  {
    const antes = fs.existsSync;
    fs.existsSync = (p) => (/setores|stats_edificacoes/.test(p) ? false : antes(p));
    let erro = null, r = null;
    try { r = await sobeApp(); } catch (e) { erro = e; }
    fs.existsSync = antes;
    afirma(!erro, 'partida não lança quando falta arquivo (' + (erro || 'ok') + ')');
    afirma(!!(r && r.mapa.camadas.has('zoneamento-fill')),
      'as camadas essenciais continuam criadas');
    afirma(!!(r && !r.mapa.camadas.has('setores-fill')),
      'a camada opcional ausente simplesmente não aparece');
    afirma(!!(r && r.FALHAS.length === 2),
      'as 2 ausências ficam registradas para o aviso na tela');
  }

  console.log('\n' + (falhas ? falhas + ' FALHA(S)' : 'todos os testes passaram'));
  process.exit(falhas ? 1 : 0);
})().catch((e) => { console.error('ERRO NO TESTE:', e); process.exit(1); });

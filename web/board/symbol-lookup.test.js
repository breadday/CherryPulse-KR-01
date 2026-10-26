const test = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {validateDirectory, searchDirectory, attach} = require('./symbol-lookup.js');
const directory = {schemaVersion: 1, fetchedAt: '2026-10-26T10:00:00Z', symbols: [
  ['005935','삼성전자우','KOSPI','주식'], ['005930','삼성전자','KOSPI','주식'],
  ['000660','SK하이닉스','KOSPI','주식'], ['069500','KODEX 200','KOSPI','ETF'],
]};
test('name search prioritizes exact common stock, preserves preferred shares and ignores spaces/case', () => {
  validateDirectory(directory);
  const result = searchDirectory(directory, '삼성전자');
  assert.equal(result.total, 2); assert.equal(result.exact[0][0], '005930');
  assert.equal(result.matches[1][0], '005935');
  assert.equal(searchDirectory(directory,'sk 하이닉스').exact[0][0], '000660');
  assert.equal(searchDirectory(directory,'코드없음').total, 0);
  assert.equal(searchDirectory(directory,'005935').exact[0][1], '삼성전자우');
});
test('published official directory contains distinct common/preferred and KOSDAQ examples', () => {
  const real = validateDirectory(JSON.parse(readFileSync(new URL('../data/symbols.json', `file://${__filename}`),'utf8')));
  assert.ok(real.symbols.length > 2000);
  assert.equal(searchDirectory(real,'삼성전자').exact[0][0], '005930');
  assert.equal(searchDirectory(real,'삼성전자우').exact[0][0], '005935');
  assert.equal(searchDirectory(real,'에코프로비엠').exact[0][0], '247540');
});
function fixture(fetcher) {
  const elements = new Map();
  function element() { return {value:'',textContent:'',children:[],listeners:{}, addEventListener(n,fn){this.listeners[n]=fn;},replaceChildren(){this.children=[];},append(child){this.children.push(child);}}; }
  for (const id of ['symbol-name','symbol-input','symbol-lookup-button','symbol-lookup-status','symbol-lookup-results','symbol-form']) elements.set(id,element());
  const doc={getElementById:id=>elements.get(id),createElement:element};
  const api=attach(doc,fetcher,{set:()=>0,clear:()=>{}});
  return {api,get:id=>elements.get(id)};
}
test('exact name fills the code, selecting preferred changes both fields, editing clears stale automatic codes', async () => {
  const f=fixture(async()=>Response.json(directory));
  f.get('symbol-name').value='삼성전자'; await f.api.lookup();
  assert.equal(f.get('symbol-input').value,'005930');
  f.get('symbol-lookup-results').children[1].listeners.click();
  assert.equal(f.get('symbol-name').value,'삼성전자우'); assert.equal(f.get('symbol-input').value,'005935');
  f.get('symbol-name').value='SK하이닉스'; f.get('symbol-name').listeners.input();
  assert.equal(f.get('symbol-input').value,'');
});
test('late responses and network errors cannot overwrite a newer name or discard manual input', async () => {
  let finish;
  const f=fixture(()=>new Promise(resolve=>{finish=resolve;}));
  f.get('symbol-name').value='삼성전자';const pending=f.api.lookup();
  f.get('symbol-name').value='SK하이닉스';f.get('symbol-name').listeners.input();
  finish(Response.json(directory)); await pending;
  assert.equal(f.get('symbol-input').value,'');
  const bad=fixture(async()=>{throw new Error('offline');});
  bad.get('symbol-name').value='삼성전자';bad.get('symbol-input').value='005930';await bad.api.lookup();
  assert.equal(bad.get('symbol-input').value,'005930');assert.match(bad.get('symbol-lookup-status').textContent,/다시 누르거나/);
});

test('browser default timers keep Window receiver for typing, Korean composition, search button and reset', async () => {
  const vm = require('node:vm');
  const elements = new Map();
  const element = () => ({value:'',textContent:'',children:[],listeners:{},addEventListener(n,fn){this.listeners[n]=fn;},replaceChildren(){this.children=[];},append(child){this.children.push(child);}});
  for (const id of ['symbol-name','symbol-input','symbol-lookup-button','symbol-lookup-status','symbol-lookup-results','symbol-form']) elements.set(id,element());
  const tasks = new Map(); let next = 0;
  const context = {windowMarker:true, document:{getElementById:id=>elements.get(id),createElement:element},
    fetch:async()=>Response.json(directory),AbortSignal,
    setTimeout:function(callback) { assert.equal(this.windowMarker,true,'setTimeout requires Window receiver');tasks.set(++next,callback);return next; },
    clearTimeout:function(id) { assert.equal(this.windowMarker,true,'clearTimeout requires Window receiver');tasks.delete(id); },
  };
  vm.runInNewContext(readFileSync(require.resolve('./symbol-lookup.js'),'utf8'),context);
  const name=elements.get('symbol-name'),code=elements.get('symbol-input');
  name.value='삼성전자';name.listeners.compositionstart();name.listeners.input();
  assert.equal(tasks.size,0);
  name.listeners.compositionend();assert.equal(tasks.size,1);
  await [...tasks.values()][0]();assert.equal(code.value,'005930');
  code.value='';await elements.get('symbol-lookup-button').listeners.click();
  assert.equal(code.value,'005930');
  elements.get('symbol-form').listeners.reset();
  assert.equal(elements.get('symbol-lookup-results').children.length,0);
});

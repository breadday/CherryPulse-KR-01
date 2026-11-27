const test = require("node:test");
const assert = require("node:assert/strict");
const {readAccount} = require("../lib/account");
const endpoint = require("../api/account");
const cash = {entr:"0000", ord_alow_amt:"00002"};
const sample = {stk_nm:"테스트", stk_cd:"A005930", evltv_prft:"-005"};
const response = (payload, headers = {}) => ({payload, headers:new Headers(headers)});
const noWait = async () => {};
test("reads cash, zero and absent fields, and all position pages", async () => {
  const sequence = [response(cash), response({acnt_evlt_remn_indv_tot:[sample]}, {"cont-yn":"Y","next-key":"next"}),
    response({acnt_evlt_remn_indv_tot:[]})];
  const result = await readAccount(async (url,body,headers) => {
    assert.equal(url,"/api/dostk/acnt");
    if (sequence.length === 1) assert.equal(headers["next-key"],"next");
    return sequence.shift();
  },async () => "fixture",noWait);
  assert.deepEqual([result.deposit,result.available,result.holdings[0].price,result.holdings[0].profit],[0,2,null,-5]);
});
test("empty holdings and missing list are distinct", async () => {
  const read = rows => readAccount(async (_,__,headers) => response(headers["api-id"]==="kt00001" ? cash : rows),noWait,noWait);
  assert.deepEqual((await read({acnt_evlt_remn_indv_tot:[]})).holdings,[]);
  await assert.rejects(read({}), /MISSING_HOLDINGS/);
});
test("account endpoint refuses unauthorized viewers and drops partial data on broker errors", async t => {
  t.mock.method(global,"fetch");
  process.env.CHERRYPLUS_ACCOUNT_VIEW_KEY = "x".repeat(40);
  process.env.CHERRYPULSE_PAPER_APP_KEY = "fixture";
  process.env.CHERRYPULSE_PAPER_APP_SECRET = "fixture";
  const res = {setHeader(){},status(n){this.code=n;return this},json(body){this.body=body}};
  await endpoint({method:"GET",headers:{}},res);
  assert.equal(res.code,401);
  assert.equal(fetch.mock.callCount(),0);
  const req = {method:"GET",headers:{authorization:"Bearer "+"x".repeat(40)}};
  fetch.mock.mockImplementation(async () => Response.json({return_code:1}));
  await endpoint(req,res);
  assert.deepEqual([res.code,res.body],[502,{error:"ACCOUNT_UNAVAILABLE"}]);
  fetch.mock.mockImplementation(async () => {throw new DOMException("timeout","TimeoutError")});
  await endpoint(req,res);
  assert.deepEqual([res.code,res.body],[504,{error:"TIMEOUT"}]);
});

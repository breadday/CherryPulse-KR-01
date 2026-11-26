const {test}=require("node:test");
const assert=require("node:assert/strict");
const {ticket,cookieName}=require("../lib/account-device");
const {confirmation,submit}=require("../lib/manual-paper-order");

test("manual sell binds the reviewed terms and blocks retries after an unknown broker outcome",async t=>{
  process.env.CHERRYPLUS_DEVICE_RPC_KEY="test-only";
  process.env.CHERRYPLUS_ACCOUNT_VIEW_KEY="test-only";
  const device="a".repeat(64);
  const req={headers:{host:"example.test",origin:"https://example.test","content-type":"application/json",
    cookie:cookieName+"="+device+"; __Host-cp-view="+ticket(device)+"; __Host-cp-reservations="+"b".repeat(64)}};
  const input={code:"403870",side:"매도",type:"지정가",schedule:"now",qty:1,price:39000};
  assert.equal(confirmation(req,{...input,schedule:"reserved"}),null);
  assert.equal(confirmation(req,{...input,side:"취소"}),null);
  assert.equal(confirmation({headers:{}},input),null);
  input.confirmation=confirmation(req,input);
  assert.equal((await submit(req,{...input,side:"매수"})).status,409);
  let claimed=false, buyClaimed=false, posts=0;
  t.mock.method(global,"fetch",async (url,opts)=>{
    const id=opts.headers["api-id"];
    if(url.endsWith("/oauth2/token")) return Response.json({return_code:0,token:"fake"});
    if(id==="kt00001") return Response.json({return_code:0,entr:"0",ord_alow_amt:"7980"});
    if(id==="kt00018") return Response.json({return_code:0,acnt_evlt_remn_indv_tot:[{stk_cd:"403870",trde_able_qty:"2"}]});
    if(url.endsWith("/cp_claim_manual_paper_buy")) {
      const result=buyClaimed?409:201;buyClaimed=true;return Response.json(result);
    }
    if(url.endsWith("/cp_claim_manual_paper_sell")) {
      const result=claimed?409:201;claimed=true;return Response.json(result);
    }
    assert.equal(url,"https://mockapi.kiwoom.com/api/dostk/ordr");
    if (id==="kt10000") {
      assert.equal(JSON.parse(opts.body).stk_cd,"093370");
      return Response.json({return_code:0,ord_no:"000789"});
    }
    assert.equal(id,"kt10001");
    posts++;
    if (JSON.parse(opts.body).ord_qty==="2") return Response.json({return_code:0,ord_no:"000123"});
    throw Error("simulated lost response");
  });
  assert.equal((await submit(req,{...input,qty:2})).status,409);
  assert.equal((await submit(req,input)).status,502);
  assert.equal((await submit(req,input)).status,409);
  assert.equal(posts,1);
  claimed=false;
  const next={...input,qty:2};
  next.confirmation=confirmation(req,next);
  assert.deepEqual(await submit(req,next),{status:200,body:{number:"000123"}});
  const buy={...input,side:"매수",code:"093370",price:7980};
  buy.confirmation=confirmation(req,buy);
  assert.deepEqual(await submit(req,buy),{status:200,body:{number:"000789"}});
  assert.equal((await submit(req,buy)).status,409);
  buy.qty=2;
  buy.confirmation=confirmation(req,buy);
  await assert.rejects(submit(req,buy),RangeError);
});

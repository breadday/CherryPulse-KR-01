const {test}=require("node:test");
const assert=require("node:assert/strict");
const {ticket,cookieName}=require("../lib/account-device");
const {review,change}=require("../lib/paper-order-change");

test("mock amendments and cancellations require the reviewed open balance and share an original-order lock",async t=>{
  process.env.CHERRYPLUS_DEVICE_RPC_KEY="offline";
  process.env.CHERRYPLUS_ACCOUNT_VIEW_KEY="offline";
  const device="a".repeat(64);
  const req={headers:{host:"offline.test",origin:"https://offline.test","content-type":"application/json",
    cookie:cookieName+"="+device+"; __Host-cp-view="+ticket(device)+"; __Host-cp-reservations="+"b".repeat(64)}};
  const row={number:"0001234",code:"023160",price:18080,remaining:2,state:"부분체결"};
  assert.equal(review(req,{...row,state:"완료"}),null);
  const input={...row,approval:review(req,row),action:"amend",newPrice:18000};
  const locks=new Set(), orders=[];
  let remaining=1,lost=false;
  t.mock.method(global,"fetch",async (url,opts)=>{
    const body=JSON.parse(opts.body);
    if (url.endsWith("/oauth2/token")) return Response.json({return_code:0,token:"offline"});
    if (opts.headers["api-id"]==="ka10075") return Response.json({return_code:0,oso:[
      {ord_no:row.number,stk_cd:row.code,oso_qty:remaining,ord_pric:row.price}]});
    if (url.endsWith("/cp_claim_order_change")) {
      if (locks.has(body.p_key)) return Response.json(409);
      locks.add(body.p_key);return Response.json(201);
    }
    assert.equal(url,"https://mockapi.kiwoom.com/api/dostk/ordr");
    orders.push([opts.headers["api-id"],body]);
    if (lost) throw Error("lost response");
    return Response.json({return_code:0,ord_no:"0002222"});
  });
  assert.equal((await change(req,input)).status,409);
  remaining=2;
  assert.equal((await change(req,{...input,number:"0009999"})).status,409);
  assert.equal((await change(req,input)).status,200);
  assert.deepEqual(orders[0],["kt10002",{dmst_stex_tp:"KRX",stk_cd:row.code,orig_ord_no:row.number,mdfy_qty:"2",mdfy_uv:"18000",mdfy_cond_uv:""}]);
  assert.equal((await change(req,{...input,action:"cancel"})).status,409);
  row.number="0002222";lost=true;
  const cancel={...row,approval:review(req,row),action:"cancel"};
  assert.equal((await change(req,cancel)).status,502);
  assert.equal((await change(req,cancel)).status,409);
  assert.deepEqual(orders[1],["kt10003",{dmst_stex_tp:"KRX",stk_cd:row.code,orig_ord_no:row.number,cncl_qty:"2"}]);
  assert.equal(orders.length,2);
});

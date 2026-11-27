const {test}=require("node:test");
const assert=require("node:assert/strict");
const {reconcile}=require("../lib/reservation-paper-order");
const record={details:{code:"023160",qty:1,price:18080,side:"매수",date:"2026-11-26"},
  startedAt:"2026-11-26T09:06:00+09:00"};
const now=new Date("2026-11-26T15:30:00+09:00");
const base={number:"00012",originalNumber:null,qty:1,price:18080,code:"023160",time:"090617",
  state:"미체결",side:"+매수",executed:0,remaining:1};
test("unknown attempt needs explicit selection from matching same-day originals",()=>{
  const rows={orders:[{...base,time:"090559",number:"00011"},base],fills:[]};
  assert.deepEqual(reconcile(record,rows,undefined,now),{candidates:[{number:"00012",time:"090617"}]});
  assert.deepEqual(reconcile(record,rows,"00011",now),{candidates:[{number:"00012",time:"090617"}]});
  assert.equal(reconcile(record,rows,"00012",now).observation.state,"unfilled");
  assert.deepEqual(reconcile(record,rows,"00012",new Date("2026-11-27T00:10:00+09:00")),{});
});
test("known number follows correction fills, retaining the original broker acceptance time",()=>{
  const filled={...base,number:"00013",originalNumber:"00012",price:18610,side:"+매수정정",
    executed:1,remaining:0,state:"완료",time:"152929"};
  const tables={orders:[],fills:[filled,base]};
  assert.deepEqual(reconcile({...record,number:"00012"},tables,undefined,now).observation,
    {number:"00012",state:"filled",executed:1,remaining:0,acceptedAt:"2026-11-26T09:06:17+09:00"});
  tables.fills=[filled];
  assert.equal(reconcile({...record,number:"00012"},tables,undefined,now).observation.acceptedAt,null);
});

test("reservation API persists dispatch and missing response; a restarted request never resends",async t=>{
  const api=require("../api/paper-orders");
  const {ticket}=require("../lib/account-device");
  const keys=["CHERRYPLUS_DEVICE_RPC_KEY","CHERRYPLUS_ACCOUNT_VIEW_KEY","CHERRYPULSE_PAPER_APP_KEY","CHERRYPULSE_PAPER_APP_SECRET"];
  const old=keys.map(key=>process.env[key]);
  for(const key of keys) process.env[key]="fixture-only-".repeat(4);
  t.after(()=>keys.forEach((key,i)=>{if(old[i]===undefined) delete process.env[key]; else process.env[key]=old[i];}));
  const device="a".repeat(64), session="b".repeat(64);
  const headers={origin:"https://fixture.test",host:"fixture.test","content-type":"application/json",
    cookie:"__Host-cp-account-device="+device+"; __Host-cp-reservations="+session+"; __Host-cp-view="+ticket(device)};
  const details={...record.details,type:"지정가"};
  const id="00000000-0000-4000-8000-000000000001";
  let attempt, dispatches=0;
  t.mock.method(global,"fetch",async(url,options)=>{
    const data=JSON.parse(options.body);
    let reply;
    if(url.endsWith("/rpc/cp_reservation_paper")) {
      assert.equal(data.p_id,id);
      switch(data.p_action) {
        case "preview": reply=attempt?{status:409}:{details}; break;
        case "claim": assert.equal(attempt,undefined); attempt={...data.p_data}; reply={details}; break;
        case "dispatch": Object.assign(attempt,data.p_data); reply={ok:true}; break;
        case "response": Object.assign(attempt,data.p_data); reply={ok:true}; break;
        default: assert.fail("unexpected ledger action");
      }
    } else if(url.endsWith("/oauth2/token")) reply={return_code:0,token:"fixture"};
    else if(options.headers["api-id"]==="kt00001") reply={return_code:0,ord_alow_amt:20000};
    else if(options.headers["api-id"]==="kt00018") reply={return_code:0,acnt_evlt_remn_indv_tot:[]};
    else if(url==="https://mockapi.kiwoom.com/api/dostk/ordr") {
      assert.ok(attempt.startedAt); dispatches++; throw Error("fixture transport timeout");
    } else assert.fail("unexpected network target");
    return Response.json(reply);
  });
  async function call(action,body) {
    const res={setHeader(){},status(n){this.statusCode=n;return this;},json(data){this.data=data;}};
    await api({method:"POST",headers,body:{id,version:1,...body},query:{action:"reservation-"+action}},res);
    return res;
  }
  const preview=await call("preview",{});
  assert.equal(preview.statusCode,200);
  assert.equal(dispatches,0);
  assert.equal((await call("submit",{})).statusCode,409);
  assert.equal((await call("submit",preview.data)).statusCode,502);
  assert.equal(attempt.state,"unknown");
  assert.ok(attempt.sentAt);
  assert.equal(attempt.receivedAt,undefined);
  assert.equal((await call("submit",preview.data)).statusCode,409);
  assert.equal(dispatches,1);
});

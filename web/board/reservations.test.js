const {test} = require("node:test");
const assert = require("node:assert/strict");
const handle = require("../api/reservations");
function send(method,headers={},body={}) {
  const res={headers:{},setHeader(k,v){this.headers[k]=v},status(s){this.code=s;return this},json(data){this.body=data}};
  return handle({method,headers,body},res).then(()=>res);
}
test("reservation API blocks unauthenticated, cross-site and non-JSON mutations",async t=>{
 const net=t.mock.method(global,"fetch");
 assert.equal((await send("GET",{authorization:"Bearer account-view-key"})).code,401);
 assert.equal((await send("DELETE")).code,415);
 assert.equal((await send("POST",{"content-type":"application/json","sec-fetch-site":"cross-site"})).code,403);
 assert.equal(net.mock.callCount(),0);
});
test("PIN login places expiring secret only in secure host cookie",async t=>{
 const fixture="a".repeat(64);
 t.mock.method(global,"fetch",async ()=>Response.json({sessionToken:fixture}));
 const res=await send("POST",{"content-type":"application/json"},{action:"login",pin:"1234"});
 assert.deepEqual(res.body,{ok:true});
 assert.match(res.headers["Set-Cookie"],/Secure; HttpOnly; SameSite=Strict/);
 assert.match(res.headers["Cache-Control"],/no-store/);
});
test("reservation updates use only the checked RPC and propagate conflicts",async t=>{
 t.mock.method(global,"fetch",async (url,options)=>{
   assert.equal(new URL(url).pathname,"/rest/v1/rpc/cp_reservations");
   assert.equal(JSON.parse(options.body).p_version,2);
   return Response.json({status:409});
 });
 const res=await send("PATCH",{"content-type":"application/json",cookie:"__Host-cp-reservations="+"b".repeat(64)},
   {id:"12345678-0000-4000-b000-000000000001",version:2});
 assert.equal(res.code,409);
});

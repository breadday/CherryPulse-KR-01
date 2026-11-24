const {test} = require("node:test");
const assert = require("node:assert/strict");
const {readFileSync} = require("node:fs");
const vm = require("node:vm");
const client = readFileSync(require.resolve("../reservation-client.js"),"utf8");

function loginFixture(responses) {
  const elements = new Map(), calls = [], button = {};
  function el(id) {
    if (!elements.has(id)) elements.set(id, {querySelector:()=>button,replaceChildren(){},focus(){},select(){}});
    return elements.get(id);
  }
  const context = {document:{getElementById:el,addEventListener(){}},window:{setInterval(){},addEventListener(){}},
    AbortSignal, fetch:async (url,options)=>{
      calls.push(options.method);
      const [status,body] = responses.shift();
      return {ok:status===200,status,json:async()=>body};
    }};
  vm.runInNewContext(client+"; CherryReservations.attach({sessionChanged(){}});",context);
  el("reservation-pin").value="012345";
  return {el,calls,submit:()=>el("reservation-login").onsubmit({preventDefault(){},currentTarget:el("reservation-login")})};
}
test("rejected login keeps PIN and explains which credential to use",async()=>{
  const f=loginFixture([[401,{}]]);
  await f.submit();
  assert.equal(f.el("reservation-pin").value,"012345");
  assert.match(f.el("reservation-status").textContent,/일치하지/);
  assert.deepEqual(f.calls,["POST"]);
});
test("login retrieves reservations before clearing PIN; lost cookie is distinct",async()=>{
  for(const status of [200,401,503]){
    const f=loginFixture([[200,{}],[status,{rows:[]}]]);
    await f.submit();
    assert.deepEqual(f.calls,["POST","GET"]);
    assert.equal(f.el("reservation-pin").value,status===200?"":"012345");
    assert.match(f.el("reservation-status").textContent,status===200?/예약 0건/:status===401?/쿠키/:/조회에 실패/);
  }
});

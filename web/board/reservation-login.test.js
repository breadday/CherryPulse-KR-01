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
  const context = {document:{getElementById:el,addEventListener(){}},window:{setInterval(){},addEventListener(){},dispatchEvent(){}},CustomEvent:class {},
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

test("reservation cards keep the dry run separate from paper order quantities and times",async()=>{
  function element() {
    return {children:[],dataset:{},textContent:"",append(...children){this.children.push(...children);},
      replaceChildren(){this.children=[];},addEventListener(){}};
  }
  const elements=new Map();
  function el(id) {if(!elements.has(id)) elements.set(id,element());return elements.get(id);}
  const row={status:"dry_run",processedAt:"2026-11-26T00:05:00Z",details:{date:"2026-11-26",time:"09:05",qty:1,price:18080,name:"태광",side:"매수",type:"지정가"}};
  const document={createElement:element,getElementById:el,addEventListener(){}};
  const context={document,window:{addEventListener(){},setInterval(){}},AbortSignal,
    fetch:async(url,options)=>options.method==="POST"
      ? {ok:false,status:409,json:async()=>({status:409})}
      : {ok:true,json:async()=>({rows:[row]})}};
  const reservations=vm.runInNewContext(client+"; CherryReservations.attach({sessionChanged(){}});",context);
  async function card() {
    await el("reservation-refresh").onclick();
    return el("reservation-list").children[0].children.map(c=>c.textContent).join("\n");
  }
  assert.match(await card(),/DRY_RUN · 주문 전송 없음/);
  assert.equal(await reservations.save("test-id",null,row.details),false);
  assert.match(el("reservation-status").textContent,/같은 조건의 예약이 이미 서버 예약 목록에/);
  row.paperOrder={state:"unknown",executed:null,remaining:null};
  assert.match(await card(),/접수 확인 필요[\s\S]*키움 접수 미확인[\s\S]*잔량 미확인/);
  for (const [state,label,executed,remaining] of [
    ["accepted","접수",null,null],["unfilled","미체결",0,2],["partial","부분체결",1,1],
    ["filled","완전체결",2,0],["rejected","거절",null,null]]) {
    row.paperOrder={state,number:"00123",executed,remaining};
    const text=await card();
    assert.ok(text.includes("키움 모의주문 · "+label));
    assert.ok(text.includes("주문번호 00123"));
    assert.equal(text.includes("주문 전송 없음"),false);
    if (executed!==null) assert.ok(text.includes("체결 "+executed+"주 · 잔량 "+remaining+"주"));
  }
});

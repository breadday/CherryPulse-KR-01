(() => {
  const el=id=>document.getElementById(id);
  const key=el("viewer-key");
  let review=0,lookup=0;
  function invalidate() {review++;el("paper-result").textContent="";}
  function clear() {
    invalidate();lookup++;el("history-tables").replaceChildren();
    el("history-state").textContent="계좌·보유종목에서 열람 키를 입력한 뒤 조회하세요.";
  }
  key.addEventListener("input",clear);
  addEventListener("account-locked",clear);
  addEventListener("holding-selected",invalidate);
  el("orders").addEventListener("input",invalidate);
  el("orders").addEventListener("click",event=>{if(event.target.closest("button")?.id!=="paper-check") invalidate();});
  async function read(path,opts) {
    if (!key.value) throw Error("계좌·보유종목에서 계좌 열람 키를 입력하세요.");
    const r=await fetch("/api/paper-orders"+path,{...opts,headers:{Authorization:"Bearer "+key.value,"Content-Type":"application/json"},
      cache:"no-store",redirect:"error",signal:AbortSignal.timeout(55000)});
    const data=await r.json();
    if (!r.ok) throw Error(data.error || "조회 실패");
    return data;
  }
  el("paper-check").onclick=async ()=>{
    const id=++review, out=el("paper-result");
    const input={code:el("symbol").value,side:el("direction").value,type:el("order-type").value,
      qty:Number(el("quantity").value.replaceAll(",","")),price:el("order-type").value==="시장가"?null:Number(el("price").value.replaceAll(",",""))};
    out.textContent="모의계좌 조회 중…";
    try {
      const data=await read("?action=prepare",{method:"POST",body:JSON.stringify(input)});
      if (id===review) out.textContent=data.apiId+" 사전검증 완료 · "+input.code+" "+input.side+" "+input.qty+"주 · 주문 전송 없음";
    } catch(e){if(id===review)out.textContent=e.message;}
  };
  function table(title,rows) {
    const heading=document.createElement("h3");heading.textContent=title;
    const wrap=document.createElement("div");wrap.className="scroll";
    if (!rows.length) wrap.textContent="조회된 내역이 없습니다.";
    else {
      const t=document.createElement("table");t.className="tbl";
      const cols={time:"보고 시각",name:"종목",number:"주문번호",originalNumber:"원주문번호",side:"구분",qty:"주문수량",executed:"체결수량",remaining:"잔량",price:"주문가",fillPrice:"체결가",state:"상태"};
      const head=t.createTHead().insertRow();
      for(const label of Object.values(cols)){const th=document.createElement("th");th.textContent=label;head.append(th);}
      const body=t.createTBody();
      for(const row of rows){
        const tr=body.insertRow();
        for(const col of Object.keys(cols)) {const v=row[col];tr.insertCell().textContent=typeof v==="number"?v.toLocaleString("ko-KR"):v??"—";}
      }
      wrap.append(t);
    }
    el("history-tables").append(heading,wrap);
  }
  el("history-refresh").onclick=async ()=>{
    const id=++lookup;
    el("history-tables").replaceChildren();el("history-state").textContent="조회 중…";
    try {
      const data=await read("",{method:"GET"});
      if(id!==lookup)return;
      table("주문내역",data.orders);table("체결조회",data.fills);
      el("history-state").textContent="키움 모의계좌 조회 완료 · KRX";
    } catch(e){if(id===lookup)el("history-state").textContent=e.message;}
  };
})();

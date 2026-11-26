(() => {
  const el=id=>document.getElementById(id);
  const key=el("viewer-key");
  let review=0,lookup=0;
  let preparedOrder=null, sending=false;
  function invalidate() {review++;preparedOrder=null;el("manual-order").hidden=true;el("paper-result").textContent="";}
  function clear() {
    invalidate();lookup++;el("history-tables").replaceChildren();
    el("history-state").textContent="계좌·보유종목에서 열람 키를 입력한 뒤 조회하세요.";
  }
  key.addEventListener("input",clear);
  addEventListener("account-locked",clear);
  addEventListener("holding-selected",invalidate);
  el("orders").addEventListener("input",invalidate);
  el("orders").addEventListener("click",event=>{if(!["paper-check","manual-order"].includes(event.target.closest("button")?.id)) invalidate();});
  async function read(path,opts) {
    const r=await fetch("/api/paper-orders"+path,{...opts,headers:{Authorization:"Bearer "+accountDevice.credential(),"Content-Type":"application/json"},
      cache:"no-store",redirect:"error",signal:AbortSignal.timeout(55000)});
    const data=await r.json();
    if (!r.ok) throw Error(data.error || "조회 실패");
    return data;
  }
  function currentInput() {
    return {manualBuy:true,code:el("symbol").value,side:el("direction").value,type:el("order-type").value,schedule:el("schedule").value,
      qty:Number(el("quantity").value.replaceAll(",","")),price:el("order-type").value==="시장가"?null:Number(el("price").value.replaceAll(",",""))};
  }
  el("paper-check").onclick=async ()=>{
    invalidate();
    const id=review, out=el("paper-result"), input=currentInput();
    out.textContent="모의계좌 조회 중…";
    try {
      const data=await read("?action=prepare",{method:"POST",body:JSON.stringify(input)});
      if (id!==review) return;
      out.textContent=data.apiId+" 사전검증 완료 · "+input.code+" "+input.side+" "+input.qty+"주 · 주문 전송 없음";
      if (data.confirmation) {
        preparedOrder={input,confirmation:data.confirmation};
        el("manual-order").textContent="키움 모의"+input.side+" 전송";
        el("manual-order").hidden=false;
      } else if (input.schedule==="now" && input.type==="지정가") {
        out.textContent+=" · 모의주문 전송은 등록 기기 PIN 로그인 후 가능합니다.";
      }
    } catch(e){if(id===review)out.textContent=e.message;}
  };
  el("manual-order").onclick=async ()=>{
    if (sending || !preparedOrder) return;
    const {input,confirmation}=preparedOrder;
    if (JSON.stringify(currentInput())!==JSON.stringify(input) || confirmation.expiry<=Date.now()) {
      invalidate();el("paper-result").textContent="조건을 다시 사전검증하세요.";return;
    }
    if (!window.confirm("키움 모의계좌 · "+el("stock-name").value+" ("+input.code+")\n"+input.qty+"주 · 지정가 "+input.price.toLocaleString("ko-KR")+"원\n이 "+input.side+" 주문을 지금 전송할까요?")) return;
    invalidate();
    sending=true;
    const id=review, out=el("paper-result");
    out.textContent="키움 모의"+input.side+" 전송 중…";
    try {
      const result=await read(input.side==="매수" ? "?action=manual-buy" : "?action=manual-sell",{method:"POST",body:JSON.stringify({...input,confirmation})});
      if (id===review) out.textContent="모의"+input.side+" 접수 · 주문번호 "+result.number+" · 주문·체결 내역에서 확인하세요.";
    } catch(e) {if(id===review) out.textContent=e.message+" · 재전송 전에 주문·체결 내역을 확인하세요.";}
    finally {sending=false;}
  };
  function changeControls(cell,row) {
    const price=document.createElement("input");
    price.type="text";price.inputMode="numeric";price.placeholder="새 지정가 (원)";
    price.setAttribute("aria-label",row.name+" 새 지정가 (원)");
    if (row.price>0) cell.append(price);
    const status=document.createElement("p");
    status.setAttribute("role","status");
    const buttons=[];
    for (const action of row.price>0?["amend","cancel"]:["cancel"]) {
      const button=document.createElement("button");
      button.type="button";button.className="btn secondary";
      button.textContent=action==="amend"?"가격 정정":"잔량 취소";
      buttons.push(button);cell.append(button);
      button.onclick=async ()=>{
        const amend=action==="amend", newPrice=Number(price.value.trim());
        if (amend && (!/^\d+$/.test(price.value.trim()) || !Number.isSafeInteger(newPrice) || newPrice<=0 || newPrice===row.price)) {
          status.textContent="기존 주문가와 다른 새 지정가를 원 단위로 입력하세요.";price.focus();return;
        }
        const terms=row.name+" · "+row.side+" · 주문번호 "+row.number+" · 잔량 "+row.remaining+"주";
        const summary=amend?row.price.toLocaleString()+"원 → "+newPrice.toLocaleString()+"원으로 정정":"잔량 전부 취소";
        if (!window.confirm("키움 모의계좌\n"+terms+"\n"+summary+" 요청을 전송할까요?")) return;
        for (const b of buttons) b.disabled=true;
        price.disabled=true;status.textContent="미체결 잔량 확인 중…";
        try {
          const result=await read("?action=change",{method:"POST",body:JSON.stringify({action,newPrice:amend?newPrice:null,
            number:row.number,code:row.code,remaining:row.remaining,price:row.price,approval:row.changeApproval})});
          status.textContent=button.textContent+" 요청 접수 · 주문번호 "+result.number+" · 오늘의 주문·체결을 다시 조회하세요.";
        } catch(e) {status.textContent=e.message+" · 오늘의 주문·체결을 다시 조회하세요.";}
      };
    }
    cell.append(status);
  }
  function table(title,rows) {
    const heading=document.createElement("h3");heading.textContent=title;
    const wrap=document.createElement("div");wrap.className="scroll";
    if (!rows.length) wrap.textContent="조회된 내역이 없습니다.";
    else {
      const t=document.createElement("table");t.className="tbl";
      const cols={time:"보고 시각",name:"종목",number:"주문번호",originalNumber:"원주문번호",side:"구분",qty:"주문수량",executed:"체결수량",remaining:"잔량",price:"주문가",fillPrice:"체결가",state:"상태"};
      const head=t.createTHead().insertRow();
      for(const label of Object.values(cols)){const th=document.createElement("th");th.textContent=label;head.append(th);}
      const editable=rows.some(row=>row.changeApproval);
      if (editable) {const th=document.createElement("th");th.textContent="주문 변경";head.append(th);}
      const body=t.createTBody();
      for(const row of rows){
        const tr=body.insertRow();
        for (const [col,label] of Object.entries(cols)) {
          const cell=tr.insertCell();
          cell.dataset.label=label;
          const value=row[col];
          cell.textContent=typeof value==="number"?value.toLocaleString("ko-KR"):value??"—";
        }
        if (editable) {
          const cell=tr.insertCell();
          if (row.changeApproval) {cell.dataset.label="주문 변경";changeControls(cell,row);}
        }
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

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
  function priceComparison(cell,row,quotes) {
    const summary=document.createElement("p"), time=document.createElement("small");
    const refresh=document.createElement("button");
    refresh.type="button";refresh.className="btn secondary";refresh.textContent="현재가 새로고침";
    summary.setAttribute("role","status");
    const orderPrice="주문가 "+row.price.toLocaleString("ko-KR")+"원";
    async function load() {
      refresh.disabled=true;
      summary.textContent=orderPrice+" · 현재가 조회 중…";time.textContent="";
      try {
        if (!quotes.has(row.code)) quotes.set(row.code,CherryPlusMarket.quote(row.code).finally(()=>quotes.delete(row.code)));
        const tick=await quotes.get(row.code);
        if (tick.code!==row.code || !Number.isSafeInteger(tick.price) || tick.price<=0 || !/^\d{14}$/.test(tick.time)) throw Error();
        const diff=tick.price-row.price;
        const comparison=diff===0?"주문가와 동일":"주문가보다 "+Math.abs(diff).toLocaleString("ko-KR")+"원 "+(diff>0?"높음":"낮음");
        summary.textContent=orderPrice+" · 현재가 "+tick.price.toLocaleString("ko-KR")+"원 ("+comparison+")";
        time.textContent=tick.time.replace(/^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})$/,"최근 체결 $1-$2-$3 $4:$5:$6 KST");
      } catch {summary.textContent=orderPrice+" · 현재가 조회 실패";}
      finally {refresh.disabled=false;}
    }
    refresh.onclick=load;
    const controls=document.createElement("div");
    controls.append(time,refresh);cell.append(summary,controls);
    load();
  }
  function changeControls(cell,row,quotes) {
    const price=document.createElement("input");
    price.type="text";price.inputMode="numeric";price.placeholder="새 지정가 (원)";
    price.setAttribute("aria-label",row.name+" 새 지정가 (원)");
    if (row.price>0) {priceComparison(cell,row,quotes);cell.append(price);}
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
      const quotes=new Map();
      for(const row of rows){
        const tr=body.insertRow();
        if (title==="주문내역") {
          const card=tr.insertCell();
          card.className="order-card";
          const amount=(n,unit)=>Number.isSafeInteger(n)?n.toLocaleString("ko-KR")+unit:"—";
          const header=document.createElement("header"),name=document.createElement("strong"),state=document.createElement("span");
          name.textContent=row.name;state.textContent=row.state;
          header.append(name,state);
          const terms=document.createElement("p"),balance=document.createElement("p");
          terms.textContent=[row.side,amount(row.qty,"주"),row.price>0?amount(row.price,"원"):"주문가 —"].join(" · ");
          balance.textContent="잔량 "+amount(row.remaining,"주")+"  ·  체결 "+amount(row.executed,"주");
          const details=document.createElement("details"),summary=document.createElement("summary"),info=document.createElement("dl");
          summary.textContent="주문 상세";
          for (const key of ["time","number","originalNumber","fillPrice"]) {
            const label=document.createElement("dt"),value=document.createElement("dd");
            label.textContent=cols[key];value.textContent=key==="fillPrice"?(row.executed>0?amount(row.fillPrice,"원"):"—"):row[key]??"—";
            info.append(label,value);
          }
          details.append(summary,info);card.append(header,terms,balance,details);
          if (row.changeApproval) {
            const actions=document.createElement("details"),toggle=document.createElement("summary");
            toggle.textContent=row.price>0?"가격 정정 · 잔량 취소":"잔량 취소";
            actions.append(toggle);card.append(actions);
            actions.addEventListener("toggle",()=>{
              if (actions.open && actions.children.length===1) changeControls(actions,row,quotes);
            });
          }
        }
        for (const [col,label] of Object.entries(cols)) {
          const cell=tr.insertCell();
          cell.dataset.label=label;
          const value=row[col];
          cell.textContent=typeof value==="number"?value.toLocaleString("ko-KR"):value??"—";
        }
        if (editable) {
          const cell=tr.insertCell();
          if (row.changeApproval) {cell.dataset.label="주문 변경";changeControls(cell,row,quotes);}
        }
      }
      wrap.append(t);
      if (title==="체결조회") {
        t.classList.add("fills-desktop");
        const list=document.createElement("table");
        list.className="fills-mobile";
        list.setAttribute("aria-label","체결조회");
        const pairs=[["name","side"],["fillPrice","price"],["executed","remaining"],["time","state"],["number","originalNumber"],["qty"]];
        function pairedCells(tr,row) {
          for (const pair of pairs) {
            const cell=document.createElement(row?"td":"th");
            if (!row) cell.scope="col";
            for (const key of pair) {
              const line=document.createElement("span");
              const value=row?.[key];
              line.textContent=row?(typeof value==="number"?value.toLocaleString("ko-KR"):value??"—"):cols[key];
              if (row && key==="side") line.className=String(value).includes("매수")?"buy":String(value).includes("매도")?"sell":"";
              cell.append(line);
            }
            tr.append(cell);
          }
        }
        pairedCells(list.createTHead().insertRow(),null);
        const entries=list.createTBody();
        for (const row of rows) pairedCells(entries.insertRow(),row);
        wrap.append(list);
      }
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

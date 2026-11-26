(() => {
  const all = selector => document.querySelectorAll(selector);
  const form = document.querySelector("#account-access");
  const field = document.querySelector("#viewer-key");
  const format = (n, unit) => Number.isSafeInteger(n) ? n.toLocaleString("ko-KR") + unit : "—";
  const columns = [["종목명·코드"], ["보유수량","quantity","주"], ["매입평균가","average","원"],
    ["현재가","price","원"], ["평가금액","value","원"], ["평가손익","profit","원"], ["매도가능수량","sellable","주"]];
  let request;
  function holdings(container, rows) {
    container.replaceChildren();
    if (!rows?.length) {
      container.textContent = rows ? "보유종목 없음" : "보유종목 미조회";
      return;
    }
    const table = document.createElement("table");
    table.className = "tbl";
    const header = table.createTHead().insertRow();
    for (const [label] of columns) {
      const th = document.createElement("th");
      th.textContent = label;
      header.append(th);
    }
    const body = table.createTBody();
    for (const row of rows) {
      const tr = body.insertRow();
      const identity = tr.insertCell();
      const button = document.createElement("button");
      button.className = "btn secondary";
      button.textContent = [row.name,row.code].filter(Boolean).join(" · ");
      button.onclick = () => window.dispatchEvent(new CustomEvent("holding-selected", {detail: row}));
      identity.append(button);
      const actions = document.createElement("div");
      actions.className = "holding-actions";
      for (const side of ["매수","매도"]) {
        const action = document.createElement("button");
        action.type = "button";
        action.className = "btn secondary";
        action.textContent = side;
        action.setAttribute("aria-label", (row.name || row.code)+" "+side);
        action.disabled = side==="매도" && row.sellable===0;
        action.onclick = () => window.dispatchEvent(new CustomEvent("holding-selected",{detail:{...row,side}}));
        actions.append(action);
      }
      identity.append(actions);
      for (const [label,key,unit] of columns.slice(1)) {
        const cell = tr.insertCell();
        cell.dataset.label = label;
        cell.textContent = format(row[key], unit);
      }
    }
    container.className = "scroll";
    container.append(table);
  }
  function render(data, status) {
    for (const el of all("[data-account-status]")) el.textContent = status;
    for (const el of all("[data-account-field]")) el.textContent = format(data?.[el.dataset.accountField],"원");
    for (const el of all("[data-account-time]")) el.textContent = data
      ? "조회시각 " + new Date(data.fetchedAt).toLocaleString("ko-KR",{timeZone:"Asia/Seoul"}) + " KST" : "조회 전";
    for (const container of all("[data-holdings]")) holdings(container, data?.holdings);
    document.querySelector("#account option").textContent = data ? "키움 모의계좌" : "모의계좌 미조회";
  }
  function lock() {
    window.dispatchEvent(new Event("account-locked"));
    request?.abort();
    field.value = "";
    render(null,"모의계좌 미조회");
  }
  window.addEventListener("unified-locked",lock);
  document.querySelector("#account-lock").onclick = async () => {
    lock();
    try {
      const response=await fetch("/api/reservations",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"logout"}),redirect:"error"});
      if (!response.ok && response.status!==401) throw Error();
      window.dispatchEvent(new Event("unified-locked"));
    } catch {render(null,"서버 로그아웃 확인 실패 · 다시 잠그기를 누르세요.");}
  };
  window.addEventListener("pagehide",lock);
  form.onsubmit = async event => {
    event.preventDefault();
    request?.abort();
    const active = request = new AbortController();
    render(null,"모의계좌 조회 중");
    try {
      const response = await fetch("/api/account",{cache:"no-store", redirect:"error",
        headers:{Authorization:"Bearer " + accountDevice.credential()}, signal:AbortSignal.any([active.signal,AbortSignal.timeout(55000)])});
      if (active.signal.aborted) return;
      if (!response.ok) {
        const message = {401:"열람 키를 확인하세요.",503:"연결 대기 · 서버의 모의 키와 화면 열람 키 설정이 필요합니다.",504:"조회 시간 초과"};
        render(null,message[response.status] || "키움 모의계좌 조회 실패");
        return;
      }
      const data = await response.json();
      if (!active.signal.aborted) render(data,"키움 모의계좌 조회 완료");
    } catch {
      if (!active.signal.aborted) render(null,"계좌 조회 실패 · 연결 상태를 확인하고 다시 조회하세요.");
    }
  };
  lock();
  fetch("/api/account", {cache:"no-store", redirect:"error", signal:AbortSignal.timeout(8000)})
    .then(async response => {
      if (response.ok) {const data=await response.json(); if(!request){field.required=false;render(data,"키움 모의계좌 조회 완료");}}
      if (!request && response.status === 503) render(null,"연결 대기 · 서버에 모의 키와 계좌 화면 열람 키가 필요합니다.");
    }).catch(() => {});
})();

(function(){
const titles={watchlist:"관심종목 · 매매 패턴",home:"통합 홈",accounts:"계좌·보유종목",orders:"주문·예약",fills:"주문·체결 내역",auto:"자동매매",ops:"운영·설정"};
function go(p){document.querySelectorAll(".page").forEach(el=>el.classList.toggle("hidden",el.id!==p));document.querySelectorAll(".nav").forEach(el=>el.classList.toggle("active",el.dataset.page===p));document.getElementById("page-title").textContent=titles[p];}
document.querySelectorAll("[data-page]").forEach(el=>el.addEventListener("click",()=>{location.hash=el.dataset.page;}));
document.querySelectorAll("[data-go]").forEach(el=>el.addEventListener("click",()=>{location.hash=el.dataset.go;}));

function restorePage() {
  const page = location.hash.slice(1);
  go(Object.hasOwn(titles, page) ? page : "home");
}
window.addEventListener("hashchange", restorePage);
restorePage();
const el=id=>document.getElementById(id);
const money=n=>n.toLocaleString("ko-KR")+"원";
const val=id=>el(id).value.trim();
const validWhole=(id,allowZero=false)=>{const raw=val(id).replace(/,/g,"");if(raw===""||!/^[0-9]+$/.test(raw))return null;const n=Number(raw);return Number.isSafeInteger(n)&&n>=(allowZero?0:1)?n:null;};
const formatDigits=v=>v.replace(/\D/g,"").replace(/\B(?=(\d{3})+(?!\d))/g,",");
document.querySelectorAll(".step-field").forEach(group => {
  const field = group.querySelector("input");
  function step(delta) {
    if (field.disabled) return;
    const current = validWhole(field.id, true);
    if (current === null && field.value !== "") return;
    const increment = field.id === "price" ? 10 : 1;
    const value = current ?? 0;
    const remainder = value % increment;
    const next = value - remainder + (delta < 0 && remainder ? 0 : delta * increment);
    if (field.id === "price" && next < 1) return;
    if (!Number.isSafeInteger(next)) return;
    field.value = String(Math.max(1, next));
    field.dispatchEvent(new Event("input", {bubbles:true}));
  }
  group.querySelectorAll("[data-step]").forEach(button => {
    button.addEventListener("click", () => step(Number(button.dataset.step)));
  });
  field.addEventListener("keydown", event => {
    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
    event.preventDefault();
    step(event.key === "ArrowUp" ? 1 : -1);
  });
});
function setMarketPriceDisabled(disabled) {
  el("price").disabled = disabled;
  document.querySelectorAll("#price + .step-buttons button").forEach(button => {button.disabled = disabled;});
}
["quantity","price","cash","cash-reserve"].forEach(id=>el(id).addEventListener("input",event=>{const field=event.target,caret=field.selectionStart??field.value.length,priorDigits=field.value.slice(0,caret).replace(/\D/g,"").length;field.value=formatDigits(field.value);let pos=0,count=0;while(pos<field.value.length&&count<priorDigits){if(/\d/.test(field.value[pos]))count++;pos++;}try{field.setSelectionRange(pos,pos);}catch(_error){}recalc();}));
function recalc(){
 const qty=validWhole("quantity"),price=validWhole("price"),cash=validWhole("cash",true),reserve=val("cash-reserve")===""?0:validWhole("cash-reserve",true),market=val("order-type")==="시장가",buy=val("direction")==="매수";
 el("remaining-title").textContent=buy?"매수 후 남는 예수금 (예비금 별도)":"보유 예수금 (매도대금 미반영)";
 const total=!market&&qty!==null&&price!==null&&Number.isSafeInteger(qty*price)?qty*price:null;
 el("order-total").textContent=total===null?"—":money(total);
 const remaining=buy?(cash!==null&&total!==null?cash-total:null):cash;
 el("cash-remaining").textContent=remaining!==null?money(remaining):"—";
 const status=el("cash-alert");
 status.style.color="#47617f"; status.style.fontWeight="normal";
 if(market){status.textContent="시장가는 체결가격이 정해지지 않아 예상 주문금액을 계산할 수 없습니다.";return;}
 if(total===null){status.textContent="정확한 지정가와 수량을 입력하면 주문금액을 계산합니다.";return;}
 if(!buy){status.textContent="매도 예상 대금 "+money(total)+" · 실제 매도가능수량과 정산 시점은 미조회입니다.";return;}
 if(cash===null){status.textContent="예상 주문금액 "+money(total)+" · 사용 가능 예수금을 입력하면 남는 금액도 계산합니다.";return;}
 if(reserve===null){status.textContent="예비금을 0원 이상으로 입력하세요.";status.style.color="#ad3a3a"; status.style.fontWeight="700";return;}
 if(cash<total+reserve){status.textContent="주의: 주문금액과 예비금 합계가 입력한 예수금을 초과합니다. 수수료 제외 계산이며 실제 주문은 불가능합니다.";status.style.color="#ad3a3a"; status.style.fontWeight="700";return;}
 status.textContent="입력한 예수금 기준 매수 가능 범위 내입니다. 주문 후 잔액 중 예비금을 제외한 여유금: "+money(cash-total-reserve)+" (수수료 제외, 실계좌 미검증).";
}
let directoryPromise;
let searchVersion = 0;
let quoteVersion = 0;
let priceEdits = 0;
el("price").addEventListener("input", () => { priceEdits++; });
async function fillLimitPrice() {
  const code = val("symbol");
  const version = ++quoteVersion;
  const edits = priceEdits;
  const status = el("quote-status");
  if (!code) return;
  status.textContent = "현재가 조회 중…";
  try {
    const tick = await CherryPlusMarket.quote(code);
    if (version !== quoteVersion) return;
    if (tick.code !== code || !Number.isSafeInteger(tick.price) || tick.price <= 0 || !/^[0-9]{14}$/.test(tick.time)) throw new Error();
    if (!el("price").disabled && edits === priceEdits) el("price").value = formatDigits(String(tick.price));
    const t = tick.time;
    status.textContent = "키움 모의 최근 체결 " + money(tick.price) + " · " + t.slice(0,4)+"-"+t.slice(4,6)+"-"+t.slice(6,8)+" "+t.slice(8,10)+":"+t.slice(10,12)+" (한국시간)";
    recalc();
  } catch {
    if (version === quoteVersion) status.textContent = "현재가 조회 실패 · 다시 불러오거나 직접 입력하세요.";
  }
}
let selectedText = "";
async function updateStockSelection() {
  const query = val("stock-name");
  if (query === selectedText && val("symbol")) return;
  const version = ++searchVersion;
  ++quoteVersion;
  el("symbol").value = "";
  el("price").value = "";
  el("quote-retry").disabled = true;
  el("quote-status").textContent = "종목 선택 대기";
  el("stock-options").replaceChildren();
  recalc();
  if (query.length < 2) return;
  try {
    if (!directoryPromise) directoryPromise = CherryPlusMarket.directory().then(CherryPulseSymbols.validateDirectory).catch(error => {directoryPromise = null; throw error;});
    const directory = await directoryPromise;
    if (version !== searchVersion) return;
    const result = CherryPulseSymbols.searchDirectory(directory, query);
    for (const row of result.matches) el("stock-options").append(new Option(row[0], row[1]));
    if (result.exact.length !== 1) {
      el("feedback").textContent = result.total ? "목록에서 종목을 선택하세요." : "검색 결과가 없습니다.";
      return;
    }
    const [code, name] = result.exact[0];
    selectedText = query;
    el("symbol").value = code;
    el("feedback").textContent = name + " · " + code;
    const originalCode = serverEdit?.details.code ?? editing?.code;
    if (originalCode && originalCode !== code) {
      createId = crypto.randomUUID();
      finishEdit({keepInputs:true});
      el("feedback").textContent = name + " · 새 예약으로 전환했습니다. 기존 예약은 유지됩니다.";
    }
    el("quote-retry").disabled = false;
    await fillLimitPrice();
  } catch {
    if (version === searchVersion) el("feedback").textContent = "종목 목록 조회 실패 · 다시 검색하세요.";
  }
}
["input","change"].forEach(event => el("stock-name").addEventListener(event, updateStockSelection));
el("stock-name").addEventListener("keydown", event => {
  if (event.key === "Enter" && !event.isComposing) {
    updateStockSelection();
    if (val("symbol")) {event.preventDefault(); el("quantity").focus();}
  }
});
el("quote-retry").addEventListener("click", fillLimitPrice);
el("order-type").addEventListener("change", () => {
  ++quoteVersion;
  const market = val("order-type") === "시장가";
  setMarketPriceDisabled(market);
  if (val("symbol")) fillLimitPrice();
});
["quantity","price","cash","cash-reserve","order-type","direction"].forEach(id=>el(id).addEventListener("input",recalc));
function koreaNow(){const parts=new Intl.DateTimeFormat("en-CA",{timeZone:"Asia/Seoul",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).formatToParts(new Date());return Object.fromEntries(parts.map(p=>[p.type,p.value]));}
// KRX domestic equities, 2026 published calendar including the June and July closures.
const closures2026 = {
 "01-01":"신정","02-16":"설 연휴","02-17":"설날","02-18":"설 연휴","03-02":"삼일절 대체공휴일",
 "05-01":"노동절","05-05":"어린이날","05-25":"부처님오신날 대체공휴일","06-03":"지방선거일",
 "07-17":"제헌절","08-17":"광복절 대체공휴일","09-24":"추석 연휴","09-25":"추석",
 "10-05":"개천절 대체공휴일","10-09":"한글날","12-25":"성탄절","12-31":"연말 휴장일"
};
function closure(date) {
 const day = new Date(date+"T00:00:00Z").getUTCDay();
 if (day===0 || day===6) return "주말";
 return date.startsWith("2026-") ? closures2026[date.slice(5)] || "" : null;
}
function nextTradingDay(date) {
 const cursor = new Date(date+"T00:00:00Z");
 let reason;
 do {
   cursor.setUTCDate(cursor.getUTCDate()+1);
   date = cursor.toISOString().slice(0,10);
   reason = closure(date);
 } while (reason);
 return reason===null ? "" : date;
}
function reservationWarning(date) {
 if (!date) return "예약 날짜를 선택하세요.";
 const reason = closure(date);
 if (reason===null) return "해당 연도 거래소 일정이 미등록 상태입니다. 거래일 확인이 필요합니다.";
 if (!reason) return "";
 const next = nextTradingDay(date);
 return reason+"로 휴장합니다. "+(next ? "다음 거래일 "+next+"을 선택하세요." : "거래소 일정이 확인된 날짜를 선택하세요.");
}
const todayKST = koreaNow();
el("schedule-date").value = nextTradingDay([todayKST.year,todayKST.month,todayKST.day].join("-"));
function updateSchedule() {
 if (!el("schedule").disabled) el("order-heading").textContent = val("schedule")==="reserved" ? "새 예약 등록" : "새 주문 입력";
 const warning = val("schedule")==="reserved" ? reservationWarning(val("schedule-date")) : "";
 const immediate = val("schedule") !== "reserved";
 el("schedule-fields").hidden = immediate;
 el("schedule-date").disabled = immediate;
 el("schedule-time").disabled = immediate;
 const help = el("schedule-help");
 help.textContent = warning || (val("schedule")==="reserved" ? "한국시간 기준 · 예약 미리보기" : "즉시 실행 미리보기");
 help.style.color = warning ? "#ad3a3a" : "";
 help.style.fontWeight = warning ? "700" : "";
 el("feedback").textContent = "";
}
el("schedule-date").addEventListener("input",updateSchedule);
el("schedule-date").addEventListener("change",updateSchedule);
el("schedule").addEventListener("change",updateSchedule);
updateSchedule();
function previewOrder(){
 const code=val("symbol"),qty=validWhole("quantity"),type=val("order-type"),price=validWhole("price"),dst=el("feedback");
 const reserved=val("schedule")==="reserved",date=val("schedule-date"),time=val("schedule-time");
 if(reserved){const now=koreaNow(),today=now.year+"-"+now.month+"-"+now.day,clock=now.hour+":"+now.minute;if(!date||!time||date<today||(date===today&&time<=clock)){dst.textContent="예약 날짜와 시간을 현재 한국시간 이후로 입력하세요.";return;}const warning=reservationWarning(date);if(warning){dst.textContent=warning;return;}}
 if(type==="지정가" && qty && price && !Number.isSafeInteger(qty*price)){dst.textContent="계산 가능한 금액 범위를 초과했습니다.";return;}
 if(!/^\d{6}$/.test(code)||qty===null||(type==="지정가"&&price===null)){
   dst.textContent="종목명 선택, 수량, 지정가를 확인하세요.";return;
 }
 dst.textContent="입력 확인: "+code+" · "+val("direction")+" "+qty+"주 · "+type+(type==="지정가"?" "+money(price)+" · 예상 주문금액 "+money(qty*price):" (금액 미확정)")+" · "+(reserved?"예약 "+date+" "+time+" KST (거래일 확인)":"즉시 주문")+" — 주문 전송 없음.";
 if(reserved) return {code,name:val("stock-name"),qty,type,price:type==="지정가"?price:null,side:val("direction"),date,time};
}
const draftPrefix = "cherryplus.reservation.v1.";
let editing = null;
let reviewed = null;
let serverEdit = null;
let createId = crypto.randomUUID();
let createDetails = null;
function clearReview() {
  reviewed = null;
  el("confirm-server").hidden = true;
  el("confirm-draft").hidden = true;
}
function finishEdit({keepInputs = false} = {}) {
  if (!keepInputs && (editing || serverEdit)) {
    ++searchVersion;
    ++quoteVersion;
    selectedText = "";
    for (const id of ["stock-name","symbol","price"]) el(id).value = "";
    el("stock-options").replaceChildren();
    el("direction").selectedIndex = el("order-type").selectedIndex = 0;
    setMarketPriceDisabled(false);
    el("quantity").value = el("quantity").defaultValue;
    el("schedule-time").value = el("schedule-time").defaultValue;
    const today = koreaNow();
    el("schedule-date").value = nextTradingDay([today.year,today.month,today.day].join("-"));
    el("quote-retry").disabled = true;
    el("quote-status").textContent = "종목 선택 대기";
    recalc();
  }
  serverEdit = null;
  editing = null;
  el("schedule").disabled = false;
  updateSchedule();
  el("preview").textContent = "입력 내용 미리보기";
  el("confirm-server").textContent = "새 서버 예약 등록";
  el("confirm-draft").textContent = "새 예약 초안 저장";
  el("stop-edit").hidden = true;
  clearReview();
}
function editDraft(key, original, row, serverRow = null) {
  clearReview();
  serverEdit = serverRow;
  editing = key ? {key, original, code:row.code} : null;
  ++searchVersion;
  ++quoteVersion;
  selectedText = row.name;
  el("stock-name").value = row.name;
  el("symbol").value = row.code;
  el("direction").value = row.side;
  el("quantity").value = formatDigits(String(row.qty));
  el("order-type").value = row.type;
  setMarketPriceDisabled(row.type === "시장가");
  el("price").value = row.price ? formatDigits(String(row.price)) : "";
  el("quote-retry").disabled = false;
  el("quote-status").textContent = "초안 복원 · 현재가 미조회";
  el("schedule").value = "reserved";
  el("schedule").disabled = true;
  el("schedule-date").value = row.date;
  el("schedule-time").value = row.time;
  updateSchedule();
  recalc();
  el("stop-edit").hidden = false;
  const target = serverRow ? "서버 예약" : "예약 초안";
  el("order-heading").textContent = target + " 수정 · " + row.name + " · " + row.date + " " + row.time;
  el("preview").textContent = "수정 내용 미리보기";
  el("confirm-server").textContent = serverRow ? "서버 예약 변경사항 저장" : "초안으로 서버 예약 등록";
  el("confirm-draft").textContent = "초안 변경사항 저장";
  el("order-heading").focus();
}
function renderDrafts() {
  const list = el("draft-list");
  list.replaceChildren();
  try {
    const keys = Object.keys(localStorage).filter(key => key.startsWith(draftPrefix));
    el("home-drafts").textContent = "브라우저 예약 초안 " + keys.length + "건";
    if (!keys.length) list.textContent = "저장된 초안이 없습니다.";
    for (const key of keys.sort()) {
      const original = localStorage.getItem(key);
      const row = JSON.parse(original);
      const item = document.createElement("div");
      item.className = "draft-row";
      const summary = document.createElement("p");
      summary.textContent = row.date + " " + row.time + " KST · " + row.name + " (" + row.code + ") · " + row.side + " " + row.qty.toLocaleString("ko-KR") + "주 · " + row.type + (row.price ? " " + money(row.price) : "");
      const edit = document.createElement("button");
      edit.className = "btn secondary";
      edit.textContent = "수정";
      edit.onclick = () => editDraft(key, original, row);
      const cancel = document.createElement("button");
      cancel.className = "btn secondary";
      cancel.textContent = "초안 취소";
      cancel.onclick = () => {
        if (!window.confirm(summary.textContent + "\n이 예약 초안을 취소할까요?")) return;
        try {
          if (localStorage.getItem(key) === original) localStorage.removeItem(key);
          else el("feedback").textContent = "다른 창에서 변경했습니다. 목록을 확인하세요.";
          if (editing?.key === key) finishEdit();
          renderDrafts();
        } catch { el("feedback").textContent = "초안을 취소하지 못했습니다."; }
      };
      item.append(summary, edit, " ", cancel);
      list.append(item);
    }
  } catch {
    list.textContent = "브라우저 저장소를 확인할 수 없습니다.";
    el("home-drafts").textContent = "예약 초안 조회 실패";
  }
}
el("orders").addEventListener("input", clearReview);
el("orders").addEventListener("change", clearReview);
el("stop-edit").onclick = () => { finishEdit(); el("order-heading").focus(); };
el("preview").onclick = () => {
  reviewed = previewOrder();
  el("confirm-draft").hidden = !reviewed || Boolean(serverEdit);
  el("confirm-server").hidden = !reviewed || !reservations.signedIn();
};
el("confirm-draft").onclick = () => {
  const current = previewOrder();
  if (!current || JSON.stringify(current) !== JSON.stringify(reviewed)) {
    clearReview();
    el("feedback").textContent += " · 입력 내용을 다시 미리보기 하세요.";
    return;
  }
  try {
    if (editing && localStorage.getItem(editing.key) !== editing.original) {
      finishEdit();
      renderDrafts();
      el("feedback").textContent = "다른 창에서 변경된 초안입니다. 목록에서 다시 선택하세요.";
      return;
    }
    const key = editing?.key || draftPrefix + crypto.randomUUID();
    localStorage.setItem(key, JSON.stringify(current));
    finishEdit();
    renderDrafts();
    el("feedback").textContent = "이 브라우저에 예약 초안을 저장했습니다. 주문 전송 없음.";
  } catch { el("feedback").textContent = "초안을 저장하지 못했습니다. 브라우저 저장 공간을 확인하세요."; }
};
const reservations = CherryReservations.attach({
  edit(row) {
    editDraft(null, null, row.details, row);
  },
  sessionChanged(active) {
    if (!active && serverEdit) finishEdit();
    el("confirm-server").hidden = !active || !reviewed;
    renderDrafts();
  }
});
el("confirm-server").onclick = async () => {
  const current = previewOrder();
  if (!current || JSON.stringify(current) !== JSON.stringify(reviewed)) {
    clearReview();
    if (current) el("feedback").textContent += " · 입력 내용을 다시 미리보기 하세요.";
    return;
  }
  const detailsKey = JSON.stringify(current);
  if (!serverEdit && createDetails !== detailsKey) {
    createId = crypto.randomUUID();
    createDetails = detailsKey;
  }
  const id = serverEdit?.id || createId;
  const saveButton = el("confirm-server");
  saveButton.disabled = true;
  el("feedback").textContent = "서버 예약을 저장하는 중입니다.";
  try {
    if (!await reservations.save(id,serverEdit?.version,current)) {
      el("feedback").textContent = el("reservation-status").textContent;
      return;
    }
    createId = crypto.randomUUID();
    finishEdit();
    el("feedback").textContent = "서버 예약을 저장했습니다. 주문 전송 없이 모의 검증합니다.";
  } finally {saveButton.disabled = false;}
};
window.addEventListener("holding-selected", ({detail}) => {
  finishEdit();
  ++searchVersion;
  ++quoteVersion;
  el("schedule").value = "now";
  updateSchedule();
  if (detail.side) {
    el("direction").value = detail.side;
    el("order-type").value = "지정가";
    setMarketPriceDisabled(false);
  }
  selectedText = detail.name || detail.code;
  el("stock-name").value = selectedText;
  el("symbol").value = detail.code;
  el("stock-options").replaceChildren();
  el("price").value = "";
  el("quantity").value = el("quantity").defaultValue;
  el("feedback").textContent = detail.side
    ? selectedText+" · "+detail.side+" · 지정가와 수량을 확인하세요."
    : selectedText+" · 거래 구분과 수량을 확인하세요.";
  el("quote-retry").disabled = false;
  recalc();
  location.hash = "orders";
  fillLimitPrice();
  requestAnimationFrame(() => el("quantity").focus());
});
window.addEventListener("storage", renderDrafts);
renderDrafts();
recalc();
})();

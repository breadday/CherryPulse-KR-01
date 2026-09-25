"use strict";
const STORAGE_KEY = "cherrypulse-board-draft-v1";
const initial = {symbols: [], patterns: []};
let state;
let symbolView = "active";
try {
  const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
  state = saved && Array.isArray(saved.symbols) && Array.isArray(saved.patterns) ? saved : initial;
} catch { state = initial; }
const $ = (id) => document.getElementById(id);
const notice = (message) => { $("notice").textContent = message; };
function save() {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); return true; }
  catch { notice("브라우저 저장이 차단되어 이 창을 닫으면 초안이 사라집니다."); return false; }
}
function detail(pattern) {
  return pattern.kind === "PRICE_AT_OR_BELOW"
    ? `최근 체결가 ${pattern.threshold}원 이하`
    : `확인된 평균 매수가 대비 ${Number(pattern.threshold) * 100}% 하락`;
}
function render() {
  const activeCount = state.symbols.filter((item) => item.archived !== true).length;
  const archivedCount = state.symbols.length - activeCount;
  $("symbol-count").textContent = `${activeCount}개 관심 · ${archivedCount}개 보관`;
  $("active-filter").setAttribute("aria-pressed", String(symbolView === "active"));
  $("archived-filter").setAttribute("aria-pressed", String(symbolView === "archived"));
  const symbols = $("symbol-list");
  const patterns = $("pattern-list");
  symbols.replaceChildren(); patterns.replaceChildren();
  const visibleSymbols = state.symbols.filter((item) =>
    symbolView === "archived" ? item.archived === true : item.archived !== true
  );
  if (!visibleSymbols.length) {
    const empty = document.createElement("p"); empty.className = "empty";
    empty.textContent = symbolView === "archived"
      ? "보관한 종목이 없습니다. 종목 카드를 보관해 두면 여기에 남습니다."
      : "등록한 종목이 없습니다. 외부에서 선택한 종목코드를 직접 입력하세요.";
    symbols.append(empty);
  }
  for (const item of visibleSymbols) {
    const card = document.createElement("article"); card.className = "card";
    const head = document.createElement("div"); head.className = "card-head";
    const identity = document.createElement("div");
    const name = document.createElement("div"); name.className = "symbol-name"; name.textContent = item.name || "종목명 미입력";
    const code = document.createElement("span"); code.className = "symbol-code"; code.textContent = item.code;
    identity.append(name, code);
    const badge = document.createElement("span"); badge.className = "badge";
    badge.textContent = item.archived === true ? "보관 · 미적용" : "미적용";
    head.append(identity, badge);
    if (item.note) {
      const note = document.createElement("p"); note.className = "symbol-note"; note.textContent = item.note;
      card.append(head, note);
    } else {
      card.append(head);
    }
    if (safeSourceUrl(item.source)) {
      const source = document.createElement("a"); source.className = "source-link";
      source.href = safeSourceUrl(item.source); source.target = "_blank";
      source.rel = "noopener noreferrer"; source.textContent = "참고 링크 열기";
      card.append(source);
    }
    const label = document.createElement("label"); label.textContent = "손절 패턴 초안";
    const select = document.createElement("select"); select.setAttribute("aria-label", `${item.code} 손절 패턴`);
    const none = document.createElement("option"); none.value = ""; none.textContent = "연결하지 않음"; select.append(none);
    for (const pattern of state.patterns) {
      const option = document.createElement("option"); option.value = pattern.id; option.textContent = `${pattern.name} · ${detail(pattern)}`; select.append(option);
    }
    select.value = state.patterns.some((p) => p.id === item.patternId) ? item.patternId : "";
    select.addEventListener("change", () => { item.patternId = select.value; save(); notice(`${item.code}의 초안을 저장했습니다. 엔진에는 적용되지 않았습니다.`); });
    card.append(label, select);
    const archive = document.createElement("button");
    archive.type = "button"; archive.className = "archive-button";
    archive.textContent = item.archived === true ? "관심 목록으로 복원" : "보관";
    archive.addEventListener("click", () => {
      item.archived = item.archived !== true;
      save(); render();
      notice(item.archived ? "종목 초안을 보관했습니다. 엔진 상태는 변경되지 않았습니다." : "종목 초안을 관심 목록으로 복원했습니다.");
    });
    card.append(archive);
    symbols.append(card);
  }
  if (!state.patterns.length) {
    const empty = document.createElement("p"); empty.className = "empty";
    empty.textContent = "저장한 손절 패턴이 없습니다."; patterns.append(empty);
  }
  for (const pattern of state.patterns) {
    const card = document.createElement("article"); card.className = "card";
    const title = document.createElement("div"); title.className = "pattern-title"; title.textContent = pattern.name;
    const description = document.createElement("p"); description.className = "pattern-detail"; description.textContent = detail(pattern);
    card.append(title, description); patterns.append(card);
  }
}
$("active-filter").addEventListener("click", () => { symbolView = "active"; render(); });
$("archived-filter").addEventListener("click", () => { symbolView = "archived"; render(); });
function safeSourceUrl(value) {
  if (!value) return "";
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : "";
  } catch { return ""; }
}
$("symbol-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const code = $("symbol-input").value.trim();
  const name = $("symbol-name").value.trim();
  const source = $("symbol-source").value.trim();
  const note = $("symbol-note").value.trim();
  if (!/^\d{6}$/.test(code)) { notice("종목코드 6자리를 입력하세요."); return; }
  if (!name) { notice("종목명을 직접 입력하세요."); return; }
  if (source && !safeSourceUrl(source)) { notice("참고 링크는 http 또는 https 주소만 사용할 수 있습니다."); return; }
  if (state.symbols.some((item) => item.code === code)) { notice("이미 등록한 종목입니다."); return; }
  state.symbols.push({code, name, source, note, patternId: "", archived: false}); save(); event.target.reset(); render();
  notice(`${name} (${code})을 초안에 추가했습니다. 감시는 시작되지 않았습니다.`);
});
$("pattern-kind").addEventListener("change", () => {
  const ratio = $("pattern-kind").value === "AVERAGE_COST_DROP";
  $("threshold-label").textContent = ratio ? "하락률 (예: 0.02 = 2%)" : "기준 가격 (원)";
  $("threshold-hint").textContent = ratio ? "원가가 확인되지 않은 보유에는 비율 손절을 적용할 수 없습니다." : "실제 시세나 매수가를 조회하지 않습니다.";
  $("pattern-threshold").value = "";
  $("pattern-threshold").placeholder = ratio ? "예: 0.02" : "예: 9800";
});
$("pattern-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const name = $("pattern-name").value.trim();
  const kind = $("pattern-kind").value;
  const threshold = $("pattern-threshold").value.trim();
  const value = Number(threshold);
  if (!name || !Number.isFinite(value) || value <= 0 || (kind === "AVERAGE_COST_DROP" && value >= 1)) {
    notice("패턴 이름과 올바른 양수 기준값을 입력하세요. 하락률은 0과 1 사이여야 합니다."); return;
  }
  state.patterns.push({id: crypto.randomUUID(), name, kind, threshold});
  save(); event.target.reset(); $("pattern-kind").dispatchEvent(new Event("change")); render();
  notice("패턴 초안을 저장했습니다. 종목에 연결해도 엔진에는 적용되지 않습니다.");
});
render();

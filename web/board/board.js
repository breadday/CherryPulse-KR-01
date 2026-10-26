"use strict";
const STORAGE_KEY = "cherrypulse-board-draft-v1";
const initial = {symbols: [], patterns: []};
const MAX_IMPORT_BYTES = 5 * 1024 * 1024;
const MAX_BACKUP_BYTES = 10 * 1024 * 1024;
const MAX_NAME_LENGTH = 100;
const MAX_NOTE_LENGTH = 1000;
const MAX_SOURCE_LENGTH = 2048;
let state;
let symbolView = "active";
let pendingBoardRestore = null;
let restoreBaseline = null;
let restoreRequest = 0;
let persistedDraft = null;
try {
  persistedDraft = localStorage.getItem(STORAGE_KEY);
  const saved = JSON.parse(persistedDraft || "null");
  state = saved && Array.isArray(saved.symbols) && Array.isArray(saved.patterns) ? saved : initial;
} catch { state = initial; }
const $ = (id) => document.getElementById(id);
const notice = (message) => { $("notice").textContent = message; };
function commitDraft(change, message) {
  const next = JSON.parse(JSON.stringify(state));
  change(next);
  const serialized = JSON.stringify(next);
  try {
    if (localStorage.getItem(STORAGE_KEY) !== persistedDraft) {
      notice("다른 탭에서 초안이 변경되었습니다. 새로고침 후 다시 수정하세요.");
      return false;
    }
    localStorage.setItem(STORAGE_KEY, serialized);
  }
  catch { notice("브라우저 저장에 실패했습니다. 기존 초안은 유지했습니다."); return false; }
  state = next;
  persistedDraft = serialized;
  notice(message);
  return true;
}
function newDraftId() {
  try {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
  } catch { /* fall through to the local generator below */ }
  const bytes = Array.from({length: 16}, () => Math.floor(Math.random() * 256));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = bytes.map((part) => part.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
function detail(pattern) {
  if (pattern.kind === "BUY_PRICE_AT_OR_BELOW") {
    return `최근 체결가 ${pattern.threshold}원 이하 매수 · 지정가 1주 고정 · 보호 평균가 대비 -3%(체결 후 확정)`;
  }
  const condition = pattern.kind === "PRICE_AT_OR_BELOW"
    ? `최근 체결가 ${pattern.threshold}원 이하`
    : `확인된 평균 매수가 대비 ${Number(pattern.threshold) * 100}% 하락`;
  const orderType = pattern.orderType === "MARKET"
    ? "시장가"
    : pattern.orderType === "LIMIT" ? "지정가 (가격 미정)" : "주문 방식 미정";
  return `${condition} · ${orderType}`;
}
function patternFamily(pattern) { return pattern.patternId || pattern.id; }
function patternVersion(pattern) {
  return Number.isInteger(pattern.version) && pattern.version >= 1 ? pattern.version : 1;
}
function patternIsActive(pattern) { return pattern.active !== false; }
function nextPatternVersion(pattern) {
  return state.patterns
    .filter((item) => patternFamily(item) === patternFamily(pattern))
    .reduce((highest, item) => Math.max(highest, patternVersion(item)), 0) + 1;
}
function render() {
  const openedCode = state.symbols.find((item) => $("drawer-" + item.code)?.open)?.code;
  const activeCount = state.symbols.filter((item) => item.archived !== true).length;
  const archivedCount = state.symbols.length - activeCount;
  if (document.getElementById("draft-count")) $("draft-count").textContent = String(activeCount);
  if (document.getElementById("draft-archived-count")) $("draft-archived-count").textContent = String(archivedCount);
  const linkedCount = state.symbols.filter((item) => item.archived !== true &&
    state.patterns.some((pattern) => pattern.id === item.patternId &&
      pattern.kind !== "BUY_PRICE_AT_OR_BELOW")).length;
  $("overview-active").textContent = String(activeCount);
  $("overview-linked").textContent = String(linkedCount);
  $("overview-unlinked").textContent = String(activeCount - linkedCount);
  $("overview-archived").textContent = String(archivedCount);
  $("overview-next").textContent = activeCount === 0
    ? "시작하기: 종목 관리에서 외부에서 고른 종목을 추가하세요."
    : activeCount > linkedCount
    ? "다음 설정: 종목 카드에서 손절 패턴 초안을 연결하세요."
    : "초안 연결 완료 · 실제 감시는 엔진 연결·수락 확인 후 가능합니다.";
  const query = $("symbol-search").value.trim().toLowerCase();
  const scopedSymbols = state.symbols.filter((item) =>
    symbolView === "archived" ? item.archived === true : item.archived !== true
  );
  const visibleSymbols = query
    ? scopedSymbols.filter((item) =>
      [item.code, item.name, item.source, item.note]
        .some((value) => typeof value === "string" && value.toLowerCase().includes(query))
    )
    : scopedSymbols;
  const totals = `${activeCount}개 관심 · ${archivedCount}개 보관`;
  $("symbol-count").textContent = query ? `${totals} · ${visibleSymbols.length}개 표시` : totals;
  $("export-symbols-json").disabled = activeCount === 0;
  $("export-symbols-csv").disabled = activeCount === 0;
  $("active-filter").setAttribute("aria-pressed", String(symbolView === "active"));
  $("archived-filter").setAttribute("aria-pressed", String(symbolView === "archived"));
  const symbols = $("symbol-list");
  const patterns = $("pattern-list");
  symbols.replaceChildren(); patterns.replaceChildren();
  if (!visibleSymbols.length) {
    const empty = document.createElement("p"); empty.className = "empty";
    empty.textContent = query
      ? "검색 결과가 없습니다. 새 종목은 ‘＋ 종목 등록’에서 종목명으로 찾아 추가하세요."
      : symbolView === "archived"
      ? "보관한 종목이 없습니다. 종목 카드를 보관해 두면 여기에 남습니다."
      : "등록한 종목이 없습니다. 종목명을 검색해 추가하세요.";
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
    const drawer = document.createElement("details"); drawer.className = "symbol-drawer";
    drawer.id = "drawer-" + item.code;
    const opener = document.createElement("summary"); opener.textContent = "상세·설정";
    opener.setAttribute("aria-label", `${item.name || item.code} 상세·설정`);
    const body = document.createElement("section"); body.className = "drawer-body";
    body.setAttribute("aria-label", `${item.code} 종목 상세 설정`);
    const drawerTitle = document.createElement("h3"); drawerTitle.textContent = `${item.name || "종목"} · ${item.code}`;
    const close = document.createElement("button"); close.type = "button";
    close.className = "drawer-close"; close.textContent = "닫기";
    close.addEventListener("click", () => { drawer.open = false; opener.focus(); });
    drawer.addEventListener("keydown", (event) => {
      if (event.key === "Escape") { drawer.open = false; opener.focus(); }
    });
    const draftHint = document.createElement("p"); draftHint.className = "hint";
    draftHint.textContent = "브라우저 초안 · 엔진 미적용 · 감시·주문 비활성";
    body.append(close, drawerTitle, draftHint);
    const linked = state.patterns.find((pattern) => pattern.id === item.patternId && pattern.kind !== "BUY_PRICE_AT_OR_BELOW");
    const rule = document.createElement("p"); rule.className = "card-rule";
    rule.textContent = linked ? `손절: ${linked.name} · v${patternVersion(linked)}${patternIsActive(linked) ? "" : " · 비활성"} · ${detail(linked)}` : "손절 패턴 미연결";
    const buyLinked = state.patterns.find((pattern) => pattern.id === item.buyPatternId && pattern.kind === "BUY_PRICE_AT_OR_BELOW");
    const buyRule = document.createElement("p"); buyRule.className = "card-buy-rule";
    buyRule.textContent = buyLinked ? `매수: ${buyLinked.name} · v${patternVersion(buyLinked)}${patternIsActive(buyLinked) ? "" : " · 비활성"} · ${detail(buyLinked)}` : "매수 패턴 미연결";
    const runtime = document.createElement("p"); runtime.className = "hint";
    runtime.textContent = "현재가 미수신 · 보유량·주문 미조회";
    card.append(head, buyRule, rule, runtime);
    if (item.note) {
      const note = document.createElement("p"); note.className = "symbol-note"; note.textContent = item.note;
      body.append(note);
    }
    if (safeSourceUrl(item.source)) {
      const source = document.createElement("a"); source.className = "source-link";
      source.href = safeSourceUrl(item.source); source.target = "_blank";
      source.rel = "noopener noreferrer"; source.textContent = "참고 링크 열기";
      body.append(source);
    }
    const label = document.createElement("label"); label.textContent = "손절 패턴 초안";
    const select = document.createElement("select"); select.id = `stop-link-${item.code}`; label.htmlFor = select.id; select.setAttribute("aria-label", `${item.code} 손절 패턴`);
    const none = document.createElement("option"); none.value = ""; none.textContent = "연결하지 않음"; select.append(none);
    for (const pattern of state.patterns) {
      if (pattern.kind === "BUY_PRICE_AT_OR_BELOW") continue;
      const option = document.createElement("option"); option.value = pattern.id;
      option.textContent = `${pattern.name} · v${patternVersion(pattern)}${patternIsActive(pattern) ? "" : " · 비활성"} · ${detail(pattern)}`;
      option.disabled = !patternIsActive(pattern) && item.patternId !== pattern.id;
      select.append(option);
    }
    select.value = state.patterns.some((p) => p.id === item.patternId) ? item.patternId : "";
    select.addEventListener("change", () => {
      const selected = select.value;
      const candidate = state.patterns.find((entry) => entry.id === selected);
      if (selected && (!candidate || candidate.kind === "BUY_PRICE_AT_OR_BELOW" ||
          (!patternIsActive(candidate) && selected !== item.patternId))) {
        select.value = item.patternId || ""; return;
      }
      if (commitDraft((next) => { next.symbols.find((entry) => entry.code === item.code).patternId = selected; },
        `${item.code}의 초안을 저장했습니다. 엔진에는 적용되지 않았습니다.`)) render();
      else select.value = item.patternId || "";
    });
    body.append(label, select);
    const buyLabel = document.createElement("label"); buyLabel.textContent = "매수 패턴 초안";
    const buySelect = document.createElement("select"); buySelect.id = `buy-link-${item.code}`; buyLabel.htmlFor = buySelect.id; buySelect.setAttribute("aria-label", `${item.code} 매수 패턴`);
    const buyNone = document.createElement("option"); buyNone.value = ""; buyNone.textContent = "연결하지 않음"; buySelect.append(buyNone);
    for (const pattern of state.patterns.filter((entry) => entry.kind === "BUY_PRICE_AT_OR_BELOW")) {
      const option = document.createElement("option"); option.value = pattern.id;
      option.textContent = `${pattern.name} · v${patternVersion(pattern)}${patternIsActive(pattern) ? "" : " · 비활성"} · ${detail(pattern)}`;
      option.disabled = !patternIsActive(pattern) && item.buyPatternId !== pattern.id;
      buySelect.append(option);
    }
    buySelect.value = buyLinked ? item.buyPatternId : "";
    buySelect.addEventListener("change", () => {
      const selected = buySelect.value;
      const candidate = state.patterns.find((entry) => entry.id === selected);
      if (selected && (!candidate || candidate.kind !== "BUY_PRICE_AT_OR_BELOW" ||
          (!patternIsActive(candidate) && selected !== item.buyPatternId))) {
        buySelect.value = item.buyPatternId || ""; return;
      }
      if (commitDraft((next) => { next.symbols.find((entry) => entry.code === item.code).buyPatternId = selected; },
        `${item.code} 매수 패턴 초안을 저장했습니다. 감시·주문은 시작되지 않았습니다.`)) render();
      else buySelect.value = item.buyPatternId || "";
    });
    body.append(buyLabel, buySelect);
    const previewForm = document.createElement("form"); previewForm.className = "stack-form symbol-preview";
    const priceLabel = document.createElement("label"); priceLabel.textContent = "가상 현재가 (원)"; priceLabel.htmlFor = `preview-price-${item.code}`;
    const priceInput = document.createElement("input"); priceInput.id = priceLabel.htmlFor;
    priceInput.type = "number"; priceInput.min = "0.000001"; priceInput.step = "any"; priceInput.required = true;
    const avgLabel = document.createElement("label"); avgLabel.textContent = "가상 평균 매수가 (비율 손절용, 선택)"; avgLabel.htmlFor = `preview-average-${item.code}`;
    const avgInput = document.createElement("input"); avgInput.id = avgLabel.htmlFor;
    avgInput.type = "number"; avgInput.min = "0.000001"; avgInput.step = "any";
    const previewButton = document.createElement("button"); previewButton.type = "submit"; previewButton.textContent = "연결한 조건 미리보기";
    const previewResult = document.createElement("p"); previewResult.className = "symbol-preview-result";
    previewResult.setAttribute("role", "status"); previewResult.setAttribute("aria-live", "polite");
    previewForm.append(priceLabel, priceInput, avgLabel, avgInput, previewButton, previewResult);
    previewForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const result = CherryPulseBuyPreview.previewSymbol(item, state.patterns, priceInput.value, avgInput.value);
      previewResult.textContent = result.ok ? `매수: ${result.buy} / 손절: ${result.stop} · ${result.message}` : result.message;
    });
    body.append(previewForm);
    const edit = document.createElement("details"); edit.className = "symbol-edit";
    const summary = document.createElement("summary"); summary.textContent = "종목 정보 수정";
    const editForm = document.createElement("form"); editForm.className = "stack-form symbol-edit-form";
    const nameId = `edit-name-${item.code}`;
    const nameLabel = document.createElement("label"); nameLabel.htmlFor = nameId; nameLabel.textContent = "종목명";
    const nameInput = document.createElement("input"); nameInput.id = nameId; nameInput.name = "name";
    nameInput.value = item.name || ""; nameInput.maxLength = 100; nameInput.required = true;
    const sourceId = `edit-source-${item.code}`;
    const sourceLabel = document.createElement("label"); sourceLabel.htmlFor = sourceId; sourceLabel.textContent = "참고 링크";
    const sourceInput = document.createElement("input"); sourceInput.id = sourceId; sourceInput.name = "source";
    sourceInput.type = "url"; sourceInput.value = item.source || ""; sourceInput.maxLength = 2048;
    const noteId = `edit-note-${item.code}`;
    const noteLabel = document.createElement("label"); noteLabel.htmlFor = noteId; noteLabel.textContent = "메모";
    const noteInput = document.createElement("textarea"); noteInput.id = noteId; noteInput.name = "note";
    noteInput.value = item.note || ""; noteInput.maxLength = 1000; noteInput.rows = 3;
    const saveEdit = document.createElement("button"); saveEdit.type = "submit"; saveEdit.textContent = "정보 저장";
    editForm.append(nameLabel, nameInput, sourceLabel, sourceInput, noteLabel, noteInput, saveEdit);
    editForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const nameValue = nameInput.value.trim();
      const sourceValue = sourceInput.value.trim();
      const noteValue = noteInput.value.trim();
      if (!nameValue || nameValue.length > MAX_NAME_LENGTH ||
        (sourceValue && (sourceValue.length > MAX_SOURCE_LENGTH || !safeSourceUrl(sourceValue))) ||
        noteValue.length > MAX_NOTE_LENGTH) {
        notice("종목명은 100자 이내로 입력하고 참고 링크는 2048자 이내의 http 또는 https 주소, 메모는 1000자 이내로 사용하세요.");
        return;
      }
      if (commitDraft((next) => {
        const entry = next.symbols.find((candidate) => candidate.code === item.code);
        entry.name = nameValue; entry.source = sourceValue; entry.note = noteValue;
      }, `${item.code}의 종목 정보를 수정했습니다. 엔진에는 적용되지 않았습니다.`)) render();
    });
    edit.append(summary, editForm); body.append(edit);
    const archive = document.createElement("button");
    archive.type = "button"; archive.className = "archive-button";
    archive.textContent = item.archived === true ? "관심 목록으로 복원" : "보관";
    archive.addEventListener("click", () => {
      const archived = item.archived !== true;
      if (commitDraft((next) => { next.symbols.find((entry) => entry.code === item.code).archived = archived; },
        archived ? "종목 초안을 보관했습니다. 엔진 상태는 변경되지 않았습니다." : "종목 초안을 관심 목록으로 복원했습니다.")) render();
    });
    body.append(archive);
    drawer.append(opener, body); card.append(drawer);
    symbols.append(card);
    if (openedCode === item.code) { drawer.open = true; close.focus(); }
  }
  if (!state.patterns.length) {
    const empty = document.createElement("p"); empty.className = "empty";
    empty.textContent = "저장한 손절 패턴이 없습니다."; patterns.append(empty);
  }
  for (const pattern of state.patterns) {
    const card = document.createElement("article"); card.className = "card";
    const title = document.createElement("div"); title.className = "pattern-title";
    title.textContent = `${pattern.name} · v${patternVersion(pattern)}${patternIsActive(pattern) ? "" : " · 비활성"}`;
    const description = document.createElement("p"); description.className = "pattern-detail"; description.textContent = detail(pattern);
    const edit = document.createElement("details"); edit.className = "pattern-edit";
    const summary = document.createElement("summary"); summary.textContent = "새 패턴 버전 만들기";
    const form = document.createElement("form"); form.className = "stack-form pattern-version-form";
    const nameId = `version-name-${pattern.id}`;
    const nameLabel = document.createElement("label"); nameLabel.htmlFor = nameId; nameLabel.textContent = "패턴 이름";
    const nameInput = document.createElement("input"); nameInput.id = nameId; nameInput.name = "name";
    nameInput.maxLength = 100; nameInput.required = true; nameInput.value = pattern.name;
    const kindId = `version-kind-${pattern.id}`;
    const kindLabel = document.createElement("label"); kindLabel.htmlFor = kindId; kindLabel.textContent = "발동 기준";
    const kindInput = document.createElement("select"); kindInput.id = kindId; kindInput.name = "kind";
    for (const [value, text] of [["PRICE_AT_OR_BELOW", "최근 체결가가 설정 가격 이하"], ["AVERAGE_COST_DROP", "확인된 평균 매수가 대비 하락률"]]) {
      const option = document.createElement("option"); option.value = value; option.textContent = text;
      kindInput.append(option);
    }
    kindInput.value = pattern.kind;
    const thresholdId = `version-threshold-${pattern.id}`;
    const thresholdLabel = document.createElement("label"); thresholdLabel.htmlFor = thresholdId;
    thresholdLabel.textContent = pattern.kind === "AVERAGE_COST_DROP" ? "하락률 (예: 0.02 = 2%)" : "기준 가격 (원)";
    const thresholdInput = document.createElement("input"); thresholdInput.id = thresholdId;
    thresholdInput.name = "threshold"; thresholdInput.type = "number"; thresholdInput.min = "0.000001";
    thresholdInput.step = "any"; thresholdInput.required = true; thresholdInput.value = pattern.threshold;
    const orderTypeId = `version-order-type-${pattern.id}`;
    const orderTypeLabel = document.createElement("label"); orderTypeLabel.htmlFor = orderTypeId;
    orderTypeLabel.textContent = "손절 주문 방식";
    const orderTypeInput = document.createElement("select"); orderTypeInput.id = orderTypeId;
    orderTypeInput.name = "orderType"; orderTypeInput.required = true;
    for (const [value, text] of [["", "선택하세요"], ["MARKET", "시장가"], ["LIMIT", "지정가"]]) {
      const option = document.createElement("option"); option.value = value; option.textContent = text;
      orderTypeInput.append(option);
    }
    orderTypeInput.value = pattern.orderType || "";
    kindInput.addEventListener("change", () => {
      thresholdLabel.textContent = kindInput.value === "AVERAGE_COST_DROP" ? "하락률 (예: 0.02 = 2%)" : "기준 가격 (원)";
    });
    const saveVersion = document.createElement("button"); saveVersion.type = "submit";
    saveVersion.textContent = `v${nextPatternVersion(pattern)} 초안 저장`;
    form.append(nameLabel, nameInput, kindLabel, kindInput, thresholdLabel, thresholdInput,
      orderTypeLabel, orderTypeInput, saveVersion);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const value = Number(thresholdInput.value);
      if (!nameInput.value.trim() || nameInput.value.trim().length > MAX_NAME_LENGTH ||
        !Number.isFinite(value) || value <= 0 ||
        (kindInput.value === "AVERAGE_COST_DROP" && value >= 1) ||
        !["MARKET", "LIMIT"].includes(orderTypeInput.value)) {
        notice("패턴 이름(100자 이내)·기준값·주문 방식을 확인하세요. 하락률은 0과 1 사이여야 합니다."); return;
      }
      const version = nextPatternVersion(pattern);
      const nextPattern = {
        id: newDraftId(), patternId: patternFamily(pattern), version, active: true,
        name: nameInput.value.trim(), kind: kindInput.value, threshold: thresholdInput.value.trim(),
        orderType: orderTypeInput.value,
      };
      if (commitDraft((next) => { next.patterns.push(nextPattern); },
        `손절 패턴 v${version} 초안을 저장했습니다. 기존 연결은 유지되며 새 버전은 종목에 다시 연결해야 합니다.`)) render();
    });
    edit.append(summary, form);
    const toggle = document.createElement("button"); toggle.type = "button";
    toggle.className = "pattern-toggle";
    toggle.textContent = patternIsActive(pattern) ? "새 연결에서 비활성화" : "다시 활성화";
    toggle.addEventListener("click", () => {
      const active = !patternIsActive(pattern);
      if (commitDraft((next) => { next.patterns.find((entry) => entry.id === pattern.id).active = active; },
        active ? "패턴 버전을 다시 활성화했습니다. 기존 종목 연결은 유지됩니다." : "패턴 버전을 비활성화했습니다. 기존 연결과 이력은 유지됩니다.")) render();
    });
    card.append(title, description, edit, toggle); patterns.append(card);
  }
  renderBuyPatterns();
}
function renderBuyPatterns() {
  const buyList = $("buy-pattern-list");
  const buyPatterns = state.patterns.filter((pattern) => pattern.kind === "BUY_PRICE_AT_OR_BELOW");
  buyList.replaceChildren();
  if (!buyPatterns.length) {
    const empty = document.createElement("p"); empty.className = "empty";
    empty.textContent = "저장한 매수 패턴이 없습니다.";
    buyList.append(empty);
    return;
  }
  for (const pattern of buyPatterns) {
    const card = document.createElement("article"); card.className = "card";
    const title = document.createElement("div"); title.className = "pattern-title";
    title.textContent = `${pattern.name}${patternIsActive(pattern) ? "" : " · 비활성"}`;
    const description = document.createElement("p"); description.className = "pattern-detail"; description.textContent = detail(pattern);
    const toggle = document.createElement("button"); toggle.type = "button";
    toggle.className = "pattern-toggle";
    toggle.textContent = patternIsActive(pattern) ? "새 연결에서 비활성화" : "다시 활성화";
    toggle.addEventListener("click", () => {
      const active = !patternIsActive(pattern);
      if (commitDraft((next) => { next.patterns.find((entry) => entry.id === pattern.id).active = active; },
        active ? "매수 패턴을 다시 활성화했습니다." : "매수 패턴을 비활성화했습니다.")) render();
    });
    card.append(title, description, toggle); buyList.append(card);
  }
}
$("active-filter").addEventListener("click", () => { symbolView = "active"; render(); });
$("archived-filter").addEventListener("click", () => { symbolView = "archived"; render(); });
$("symbol-search").addEventListener("input", render);
function downloadActiveSymbols(format) {
  const symbols = CherryPulseDraftImport.exportActiveSymbols(state.symbols);
  if (!symbols.length) { notice("내보낼 관심종목이 없습니다."); return; }
  const isCsv = format === "csv";
  const content = isCsv
    ? CherryPulseDraftImport.exportActiveSymbolsCsv(state.symbols)
    : JSON.stringify(symbols, null, 2);
  const mimeType = isCsv ? "text/csv;charset=utf-8" : "application/json;charset=utf-8";
  const extension = isCsv ? "csv" : "json";
  const blob = new Blob([content], {type: mimeType});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `cherrypulse-symbols-${new Date().toISOString().slice(0, 10)}.${extension}`;
  link.hidden = true;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
  notice(`${symbols.length}개 관심종목 ${extension.toUpperCase()}을 내보냈습니다. 패턴 연결은 포함하지 않았습니다.`);
}
$("export-symbols-json").addEventListener("click", () => downloadActiveSymbols("json"));
$("export-symbols-csv").addEventListener("click", () => downloadActiveSymbols("csv"));
$("export-board-backup").addEventListener("click", () => {
  let content;
  try {
    content = CherryPulseBoardBackup.serializeBoardBackup(state);
  } catch (error) {
    notice(boardBackupErrorMessage(error));
    return;
  }
  const blob = new Blob([content], {type: "application/json;charset=utf-8"});
  if (blob.size > MAX_BACKUP_BYTES) {
    notice("전체 보드 백업이 10 MiB를 초과해 지원하지 않는 크기입니다.");
    return;
  }
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `cherrypulse-board-backup-${new Date().toISOString().slice(0, 10)}.json`;
  link.hidden = true;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
  notice("전체 보드 초안 JSON 백업을 다운로드했습니다. 엔진 설정은 포함되지 않습니다.");
});

function boardBackupErrorMessage(error) {
  const messages = {
    BACKUP_JSON_INVALID: "백업 JSON을 읽을 수 없습니다.",
    BACKUP_ROOT_INVALID: "백업의 최상위 구조가 올바르지 않습니다.",
    BACKUP_FIELDS_INVALID: "백업에 지원하지 않는 필드가 있습니다.",
    BACKUP_FORMAT_UNSUPPORTED: "CherryPulse 전체 보드 백업 형식이 아닙니다.",
    BACKUP_SCHEMA_UNSUPPORTED: "지원하지 않는 백업 schemaVersion입니다.",
    BACKUP_COLLECTIONS_INVALID: "종목 또는 패턴 배열이 없습니다.",
    BACKUP_SYMBOL_INVALID: "종목 코드·이름·필드를 확인하세요.",
    BACKUP_DUPLICATE_SYMBOL: "중복된 종목코드가 있습니다.",
    BACKUP_FIELD_INVALID: "링크·메모·연결 또는 보관 필드가 올바르지 않습니다.",
    BACKUP_PATTERN_INVALID: "손절 패턴 필드를 확인하세요.",
    BACKUP_DUPLICATE_PATTERN_ID: "중복된 패턴 ID가 있습니다.",
    BACKUP_PATTERN_REVISION_INVALID: "패턴 계열 또는 버전 정보가 올바르지 않습니다.",
    BACKUP_DUPLICATE_PATTERN_VERSION: "같은 패턴 계열에 중복된 버전이 있습니다.",
    BACKUP_THRESHOLD_INVALID: "손절 기준값이 올바르지 않습니다.",
    BACKUP_ORDER_TYPE_INVALID: "손절 주문 방식은 시장가 또는 지정가여야 합니다.",
    BACKUP_PATTERN_LINK_KIND: "매수·손절 패턴 연결 종류가 일치하지 않습니다.",
    BACKUP_PATTERN_LINK_MISSING: "종목이 연결된 패턴 ID를 백업에서 찾을 수 없습니다.",
  };
  const message = messages[error?.code] || "전체 보드 백업을 검증하지 못했습니다.";
  return error?.path ? `${message} (${error.path})` : message;
}

const restoreForm = $("restore-board-backup-form");
const restoreInput = $("board-backup-file");
const restoreConfirmation = $("restore-confirmation");
restoreInput.addEventListener("change", () => {
  restoreRequest += 1;
  pendingBoardRestore = null;
  restoreBaseline = null;
  restoreConfirmation.hidden = true;
});
restoreForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const request = ++restoreRequest;
  pendingBoardRestore = null;
  restoreBaseline = null;
  restoreConfirmation.hidden = true;
  const file = restoreInput.files?.[0];
  if (!file) { notice("전체 보드 백업 JSON 파일을 선택하세요."); return; }
  try {
    if (file.size > MAX_BACKUP_BYTES) {
      throw Object.assign(new Error(), {code: "BACKUP_FILE_TOO_LARGE"});
    }
    const parsed = CherryPulseBoardBackup.parseBoardBackup(await file.text());
    if (request !== restoreRequest) return;
    if (restoreInput.files?.[0] !== file) {
      notice("복원 중 선택 파일이 변경되었습니다. 새 파일을 다시 검사하세요.");
      return;
    }
    pendingBoardRestore = parsed;
    restoreBaseline = JSON.stringify(state);
  } catch (error) {
    if (request !== restoreRequest) return;
    pendingBoardRestore = null;
    notice(error?.code === "BACKUP_FILE_TOO_LARGE"
      ? "전체 보드 백업은 10 MiB 이하만 복원할 수 있습니다."
      : boardBackupErrorMessage(error));
    return;
  }
  const summary = CherryPulseBoardBackup.backupSummary(pendingBoardRestore);
  $("restore-summary").textContent =
    `${summary.symbols}개 종목(보관 ${summary.archivedSymbols}개), 손절 패턴 ${summary.patterns}개(비활성 ${summary.inactivePatterns}개)를 검증했습니다.`;
  restoreConfirmation.hidden = false;
  notice("백업 전체 검증이 통과했습니다. 현재 초안을 대체할지 확인하세요.");
});
$("cancel-board-restore").addEventListener("click", () => {
  restoreRequest += 1;
  pendingBoardRestore = null;
  restoreBaseline = null;
  restoreConfirmation.hidden = true;
  restoreForm.reset();
  notice("전체 보드 복원을 취소했습니다. 기존 초안은 변경되지 않았습니다.");
});
$("confirm-board-restore").addEventListener("click", () => {
  if (!pendingBoardRestore) return;
  try {
    if (JSON.stringify(state) !== restoreBaseline ||
      localStorage.getItem(STORAGE_KEY) !== restoreBaseline) {
      pendingBoardRestore = null;
      restoreBaseline = null;
      restoreConfirmation.hidden = true;
      notice("검사 후 현재 초안이 변경되었습니다. 백업 파일을 다시 검사하세요.");
      return;
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(pendingBoardRestore));
  } catch {
    notice("브라우저 저장에 실패했습니다. 기존 화면과 초안은 유지했습니다.");
    return;
  }
  const restored = pendingBoardRestore;
  pendingBoardRestore = null;
  restoreBaseline = null;
  state = restored;
  persistedDraft = JSON.stringify(restored);
  symbolView = "active";
  $("symbol-search").value = "";
  restoreConfirmation.hidden = true;
  restoreForm.reset();
  render();
  notice("전체 보드 초안을 복원했습니다. 엔진 적용·감시·주문은 시작되지 않았습니다.");
});

$("log-view-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const box = $("log-view-result");
  box.replaceChildren();
  const file = $("log-view-file").files && $("log-view-file").files[0];
  if (!file) { notice("로그 파일을 선택하세요."); return; }
  try {
    const api = typeof CherryPulseLogView !== "undefined"
      ? CherryPulseLogView
      : (typeof globalThis !== "undefined" ? globalThis.CherryPulseLogView : null);
    const summary = api.parseLogText(await file.text());
    const card = document.createElement("article"); card.className = "card";
    const title = document.createElement("div"); title.className = "pattern-title";
    title.textContent = "실측 요약 · 주문 전송 없음";
    card.append(title);
    if (summary.probe) {
      for (const item of summary.probe.queries) {
        const line = document.createElement("p"); line.className = "pattern-detail";
        line.textContent = `${item.api_id}: ${item.complete ? "완료" : "미완료"} · ${item.pages}페이지 · ${item.observed_rows}행 · ${item.reason || "사유 없음"}`;
        card.append(line);
      }
    }
    if (summary.submit) {
      const line = document.createElement("p"); line.className = "pattern-detail";
      line.textContent = summary.submit.acked
        ? "모의 주문 접수됨."
        : summary.submit.submitted
          ? `주문 거절(코드 ${String(summary.submit.broker_code)}) · ${summary.submit.broker_message || summary.submit.reason || "사유 없음"}.`
          : "미리보기만(전송 없음).";
      card.append(line);
    }
    if (summary.linkage) {
      const total = Object.values(summary.linkage.row_counts).reduce((a, b) => a + b, 0);
      const line = document.createElement("p"); line.className = "pattern-detail";
      line.textContent = total > 0 ? `이력 ${total}행 관측 · ${summary.linkage.reason || ""}.` : `이력 0행 · ${summary.linkage.reason || ""}.`;
      card.append(line);
    }
    box.append(card);
    notice("로그 요약을 표시했습니다. 주문을 보내지 않았습니다.");
  } catch {
    notice("로그를 읽지 못했습니다. 바탕화면 날짜 로그 파일을 확인하세요.");
  }
});

$("buy-preview-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const box = $("buy-preview-result");
  box.replaceChildren();
  const api = typeof CherryPulseBuyPreview !== "undefined"
    ? CherryPulseBuyPreview
    : (typeof globalThis !== "undefined" ? globalThis.CherryPulseBuyPreview : null);
  if (!api) { notice("미리보기 모듈을 읽지 못했습니다."); return; }
  const result = api.previewBuy(state.patterns, $("buy-preview-price").value);
  const card = document.createElement("article"); card.className = "card";
  const text = document.createElement("p"); text.className = "pattern-detail";
  if (!result.ok) {
    text.textContent = "0보다 큰 가격을 입력하세요. 시세를 조회하지 않습니다.";
  } else if (!result.hits.length) {
    text.textContent = "발동되는 매수 패턴 초안이 없습니다. 주문을 보내지 않았습니다.";
  } else {
    text.textContent = `발동 초안 ${result.hits.length}개: ${result.hits.join(", ")}. 주문을 보내지 않았습니다.`;
  }
  card.append(text);
  box.append(card);
});

function safeSourceUrl(value) {
  if (!value) return "";
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : "";
  } catch { return ""; }
}
function importErrorMessage(error) {
  const messages = {
    IMPORT_FILE_TYPE_UNSUPPORTED: "JSON 또는 CSV 파일만 가져올 수 있습니다.",
    IMPORT_FILE_TOO_LARGE: "가져오기 파일은 5 MiB 이하만 지원합니다.",
    IMPORT_JSON_INVALID: "JSON 파일을 읽을 수 없습니다.",
    IMPORT_JSON_ARRAY_REQUIRED: "JSON 최상위 값은 종목 객체 배열이어야 합니다.",
    IMPORT_CSV_INVALID: "CSV 인용부호·열 수·행 형식을 확인하세요.",
    IMPORT_CSV_HEADER_INVALID: "CSV 첫 행은 code,name을 포함하고 source,note만 추가할 수 있습니다.",
    IMPORT_FIELDS_INVALID: "지원하지 않는 필드가 있습니다. code,name,source,note만 사용하세요.",
    IMPORT_SYMBOL_INVALID: "종목코드·종목명·링크·메모 형식 또는 길이를 확인하세요.",
    IMPORT_DUPLICATE_SYMBOL: "이미 등록했거나 파일 안에서 중복된 종목코드가 있습니다.",
    IMPORT_EMPTY: "가져올 종목 행이 없습니다.",
  };
  const message = messages[error?.code] || "파일을 읽거나 검증하지 못했습니다.";
  return error?.recordNumber ? `${message} (행 ${error.recordNumber})` : message;
}

$("bulk-import-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const file = $("symbol-import-file").files?.[0];
  if (!file) { notice("JSON 또는 CSV 파일을 선택하세요."); return; }
  let imported;
  try {
    if (file.size > MAX_IMPORT_BYTES) throw Object.assign(new Error(), {code: "IMPORT_FILE_TOO_LARGE"});
    imported = CherryPulseDraftImport.parseSymbolImport(
      file.name, await file.text(), state.symbols,
    );
  } catch (error) {
    notice(importErrorMessage(error));
    return;
  }
  if (commitDraft((next) => { next.symbols.push(...imported); },
    `${imported.length}개 종목을 브라우저 초안에 추가했습니다. 감시나 주문은 시작되지 않았습니다.`)) {
    form.reset(); render();
  }
});

$("symbol-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const code = $("symbol-input").value.trim();
  const name = $("symbol-name").value.trim();
  const source = $("symbol-source").value.trim();
  const note = $("symbol-note").value.trim();
  if (!/^\d{6}$/.test(code)) { notice("종목코드 6자리를 입력하세요."); return; }
  if (!name || name.length > MAX_NAME_LENGTH) { notice("종목명은 100자 이내로 직접 입력하세요."); return; }
  if (source && (source.length > MAX_SOURCE_LENGTH || !safeSourceUrl(source))) { notice("참고 링크는 2048자 이내의 http 또는 https 주소만 사용할 수 있습니다."); return; }
  if (note.length > MAX_NOTE_LENGTH) { notice("메모는 1000자 이내로 입력하세요."); return; }
  if (state.symbols.some((item) => item.code === code)) { notice("이미 등록한 종목입니다."); return; }
  if (commitDraft((next) => {
    next.symbols.push({code, name, source, note, patternId: "", archived: false});
  }, `${name} (${code})을 초안에 추가했습니다. 감시는 시작되지 않았습니다.`)) {
    event.target.reset(); render();
  }
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
  const orderType = $("pattern-order-type").value;
  const value = Number(threshold);
  if (!name || name.length > MAX_NAME_LENGTH || !Number.isFinite(value) || value <= 0 || (kind === "AVERAGE_COST_DROP" && value >= 1) ||
    !["MARKET", "LIMIT"].includes(orderType)) {
    notice("패턴 이름은 100자 이내로 입력하고 기준값과 시장가·지정가 주문 방식을 확인하세요. 하락률은 0과 1 사이여야 합니다."); return;
  }
  const id = newDraftId();
  if (commitDraft((next) => {
    next.patterns.push({id, patternId: id, version: 1, active: true, name, kind, threshold, orderType});
  }, "패턴 초안을 저장했습니다. 종목에 연결해도 엔진에는 적용되지 않습니다.")) {
    event.target.reset(); $("pattern-kind").dispatchEvent(new Event("change")); render();
  }
});
const MAX_BUY_TARGET_PRICE = 100000;
$("buy-pattern-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const name = $("buy-pattern-name").value.trim();
  const target = $("buy-target-price").value.trim();
  const value = Number(target);
  if (!name || name.length > MAX_NAME_LENGTH) { notice("매수 패턴 이름은 100자 이내로 입력하세요."); return; }
  if (!target || !Number.isFinite(value) || value <= 0) { notice("매수 목표가는 0보다 큰 숫자로 입력하세요."); return; }
  if (value > MAX_BUY_TARGET_PRICE) { notice("목표가가 금액 상한(10만원)을 초과해 저장할 수 없습니다."); return; }
  const id = newDraftId();
  if (commitDraft((next) => {
    next.patterns.push({id, patternId: id, version: 1, active: true, name, kind: "BUY_PRICE_AT_OR_BELOW", threshold: target, orderType: "LIMIT"});
  }, "매수 패턴 초안을 저장했습니다. 엔진에는 적용되지 않습니다.")) {
    event.target.reset(); render();
  }
});
render();

// Cloud persistence is an explicit action; local edits continue to use commitDraft.
if (typeof CherryPulseCloud !== "undefined") {
  const cloud = CherryPulseCloud.createClient(fetch, () => crypto.randomUUID(), CherryPulseBoardBackup);
  let busy = false, candidate = null, baseline = null;
  const setStatus = text => {
    $("cloud-status").textContent = text;
    $("cloud-status").setAttribute("tabindex", "-1");
  };
  const actionIds = ["cloud-login", "cloud-save", "cloud-load", "cloud-retry", "cloud-logout", "cloud-confirm-load", "cloud-cancel-load"];
  const messages = {
    UNAUTHENTICATED: "접속이 만료됐습니다. 4자리 비밀번호를 다시 입력하세요. 브라우저 초안은 유지됩니다.",
    PIN_INCORRECT: "비밀번호가 일치하지 않습니다. 숫자 4자리를 확인하세요.",
    PIN_FORMAT_INVALID: "비밀번호는 숫자 4자리로 입력하세요.",
    PIN_LOCKED: "비밀번호를 5회 연속 잘못 입력해 15분간 잠겼습니다. 잠시 후 다시 시도하세요.",
    PIN_NOT_CONFIGURED: "서버 비밀번호 설정이 아직 완료되지 않았습니다.",
    LOAD_REQUIRED: "먼저 서버 초안을 확인하고 불러오세요. 기존 서버 내용을 바로 덮어쓰지 않습니다.",
    VERSION_CONFLICT: "다른 기기에서 서버 초안을 수정했습니다. 다시 확인·불러오기 후 저장하세요.",
    SAVE_UNCONFIRMED: "이전 저장 결과가 미확인입니다. ‘미확인 저장 재시도’로 같은 내용을 확인하세요.",
    NETWORK_ERROR: "응답을 받지 못했습니다. 저장 중이었다면 ‘미확인 저장 재시도’를 사용하세요.",
    DATABASE_UNAVAILABLE: "서버 응답을 확인하지 못했습니다. 잠시 후 다시 시도하세요.",
    RATE_LIMITED: "저장 요청 한도를 초과했습니다. 잠시 후 다시 시도하세요.",
    NOT_CONFIGURED: "서버 연결 설정이 아직 준비되지 않았습니다.",
  };
  function controls() {
    for (const id of actionIds) $(id).disabled = busy || (id !== "cloud-login" && !cloud.signedIn());
    $("cloud-pin").disabled = busy || cloud.signedIn();
    $("cloud-login").disabled = busy || cloud.signedIn();
  }
  async function run(action) {
    if (busy) return;
    busy = true; controls(); $("cloud-login-form").setAttribute("aria-busy", "true");
    try { await action(); }
    catch (error) { setStatus(messages[error.code] || "요청을 처리하지 못했습니다. 기존 브라우저 초안은 유지됩니다."); }
    finally {
      busy = false; controls(); $("cloud-login-form").setAttribute("aria-busy", "false");
      $("cloud-login").textContent = "보드 열기";
    }
  }
  async function login() {
    candidate = null; baseline = null; $("cloud-load-confirmation").hidden = true;
    const pin = $("cloud-pin").value;
    setStatus("비밀번호 확인 중입니다… 잠시 기다려 주세요."); $("cloud-login").textContent = "확인 중…";
    try {
      await cloud.auth(pin);
      setStatus("보드 접속 완료 · 서버 초안 확인 중…");
      const remote = await cloud.inspect();
      setStatus(remote.revision === 0 ? "보드 접속 완료 · 서버 초안 없음. 현재 초안을 서버에 저장할 수 있습니다." : `보드 접속 완료 · 서버 버전 ${remote.revision}. ‘서버 초안 확인’ 후 불러오세요.`);
    } finally { $("cloud-pin").value = ""; }
  }
  $("cloud-login-form").addEventListener("submit", event => {
    event.preventDefault();
    if (busy) return;
    if (!/^[0-9]{4}$/.test($("cloud-pin").value)) {
      setStatus("비밀번호는 숫자 4자리로 입력하세요."); $("cloud-pin").focus(); return;
    }
    return run(login);
  });
  $("cloud-logout").addEventListener("click", () => run(async () => {
    candidate = null; baseline = null; $("cloud-load-confirmation").hidden = true;
    try { await cloud.logout(); }
    finally { setStatus("이 페이지에서 로그아웃했습니다. 브라우저 초안은 유지됩니다."); }
  }));
  $("cloud-save").addEventListener("click", () => run(async () => {
    const version = await cloud.save(state);
    candidate = null; $("cloud-load-confirmation").hidden = true;
    setStatus(`서버 버전 ${version.revision} 저장 완료 · 엔진 미적용`);
  }));
  $("cloud-retry").addEventListener("click", () => run(async () => {
    const version = await cloud.retry();
    setStatus(`이전 저장 버전 ${version.revision} 확인 완료. 그 후 브라우저에서 수정했다면 다시 서버에 저장하세요.`);
  }));
  $("cloud-load").addEventListener("click", () => run(async () => {
    candidate = null; $("cloud-load-confirmation").hidden = true;
    const remote = await cloud.load();
    if (!remote.snapshot) { cloud.acceptLoaded(remote); setStatus("서버 초안이 없습니다. 현재 초안을 저장할 수 있습니다."); return; }
    candidate = remote; baseline = JSON.stringify(state);
    const summary = CherryPulseBoardBackup.backupSummary(remote.snapshot);
    $("cloud-load-summary").textContent = `서버 버전 ${remote.revision} · 종목 ${summary.symbols}개 · 패턴 ${summary.patterns}개`;
    $("cloud-load-confirmation").hidden = false;
    setStatus("서버 초안 확인 완료 · 아직 브라우저 초안을 변경하지 않았습니다.");
  }));
  $("cloud-confirm-load").addEventListener("click", () => run(async () => {
    if (!candidate) return;
    if (JSON.stringify(state) !== baseline || localStorage.getItem(STORAGE_KEY) !== persistedDraft) {
      candidate = null; $("cloud-load-confirmation").hidden = true;
      setStatus("확인 후 브라우저 초안이 바뀌었습니다. 서버 초안을 다시 확인하세요."); return;
    }
    const parsed = CherryPulseBoardBackup.parseBoardBackup(JSON.stringify(candidate.snapshot));
    const next = {symbols: parsed.symbols, patterns: parsed.patterns};
    const serialized = JSON.stringify(next);
    localStorage.setItem(STORAGE_KEY, serialized);
    state = next; persistedDraft = serialized;
    cloud.acceptLoaded(candidate);
    candidate = null; baseline = null; $("cloud-load-confirmation").hidden = true;
    symbolView = "active"; $("symbol-search").value = ""; render();
    setStatus("서버 초안을 브라우저로 불러왔습니다. 엔진 미적용 · 감시·주문 미동작");
  }));
  $("cloud-cancel-load").addEventListener("click", () => {
    candidate = null; baseline = null; $("cloud-load-confirmation").hidden = true;
    setStatus("불러오기를 취소했습니다. 브라우저 초안은 유지됩니다.");
  });
  controls();
  $("cloud-login-form").setAttribute("data-cloud-ready", "true");
  setStatus("숫자 4자리 비밀번호를 입력하고 ‘보드 열기’를 누르세요.");
}

"use strict";
const STORAGE_KEY = "cherrypulse-board-draft-v1";
const initial = {symbols: [], patterns: []};
const MAX_IMPORT_BYTES = 5 * 1024 * 1024;
const MAX_BACKUP_BYTES = 10 * 1024 * 1024;
let state;
let symbolView = "active";
let pendingBoardRestore = null;
let restoreBaseline = null;
let restoreRequest = 0;
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
function saveAndNotify(message) {
  if (save()) notice(message);
}
function detail(pattern) {
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
  const activeCount = state.symbols.filter((item) => item.archived !== true).length;
  const archivedCount = state.symbols.length - activeCount;
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
      ? "검색 결과가 없습니다. 종목명·코드·링크·메모를 확인하세요."
      : symbolView === "archived"
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
      const option = document.createElement("option"); option.value = pattern.id;
      option.textContent = `${pattern.name} · v${patternVersion(pattern)}${patternIsActive(pattern) ? "" : " · 비활성"} · ${detail(pattern)}`;
      option.disabled = !patternIsActive(pattern) && item.patternId !== pattern.id;
      select.append(option);
    }
    select.value = state.patterns.some((p) => p.id === item.patternId) ? item.patternId : "";
    select.addEventListener("change", () => {
      item.patternId = select.value;
      saveAndNotify(`${item.code}의 초안을 저장했습니다. 엔진에는 적용되지 않았습니다.`);
    });
    card.append(label, select);
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
      if (!nameValue || (sourceValue && !safeSourceUrl(sourceValue))) {
        notice("종목명을 입력하고 참고 링크는 http 또는 https 주소를 사용하세요.");
        return;
      }
      item.name = nameValue; item.source = sourceValue; item.note = noteInput.value.trim();
      saveAndNotify(`${item.code}의 종목 정보를 수정했습니다. 엔진에는 적용되지 않았습니다.`);
      render();
    });
    edit.append(summary, editForm); card.append(edit);
    const archive = document.createElement("button");
    archive.type = "button"; archive.className = "archive-button";
    archive.textContent = item.archived === true ? "관심 목록으로 복원" : "보관";
    archive.addEventListener("click", () => {
      item.archived = item.archived !== true;
      saveAndNotify(item.archived ? "종목 초안을 보관했습니다. 엔진 상태는 변경되지 않았습니다." : "종목 초안을 관심 목록으로 복원했습니다.");
      render();
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
      if (!nameInput.value.trim() || !Number.isFinite(value) || value <= 0 ||
        (kindInput.value === "AVERAGE_COST_DROP" && value >= 1) ||
        !["MARKET", "LIMIT"].includes(orderTypeInput.value)) {
        notice("패턴 이름·기준값·주문 방식을 확인하세요. 하락률은 0과 1 사이여야 합니다."); return;
      }
      const version = nextPatternVersion(pattern);
      state.patterns.push({
        id: crypto.randomUUID(), patternId: patternFamily(pattern), version, active: true,
        name: nameInput.value.trim(), kind: kindInput.value, threshold: thresholdInput.value.trim(),
        orderType: orderTypeInput.value,
      });
      saveAndNotify(`손절 패턴 v${version} 초안을 저장했습니다. 기존 연결은 유지되며 새 버전은 종목에 다시 연결해야 합니다.`);
      render();
    });
    edit.append(summary, form);
    const toggle = document.createElement("button"); toggle.type = "button";
    toggle.className = "pattern-toggle";
    toggle.textContent = patternIsActive(pattern) ? "새 연결에서 비활성화" : "다시 활성화";
    toggle.addEventListener("click", () => {
      pattern.active = !patternIsActive(pattern);
      saveAndNotify(pattern.active ? "패턴 버전을 다시 활성화했습니다. 기존 종목 연결은 유지됩니다." : "패턴 버전을 비활성화했습니다. 기존 연결과 이력은 유지됩니다.");
      render();
    });
    card.append(title, description, edit, toggle); patterns.append(card);
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
  symbolView = "active";
  $("symbol-search").value = "";
  restoreConfirmation.hidden = true;
  restoreForm.reset();
  render();
  notice("전체 보드 초안을 복원했습니다. 엔진 적용·감시·주문은 시작되지 않았습니다.");
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
  state.symbols.push(...imported);
  const saved = save(); form.reset(); render();
  if (saved) notice(`${imported.length}개 종목을 브라우저 초안에 추가했습니다. 감시나 주문은 시작되지 않았습니다.`);
});

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
  state.symbols.push({code, name, source, note, patternId: "", archived: false});
  const saved = save(); event.target.reset(); render();
  if (saved) notice(`${name} (${code})을 초안에 추가했습니다. 감시는 시작되지 않았습니다.`);
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
  if (!name || !Number.isFinite(value) || value <= 0 || (kind === "AVERAGE_COST_DROP" && value >= 1) ||
    !["MARKET", "LIMIT"].includes(orderType)) {
    notice("패턴 이름, 기준값과 시장가·지정가 주문 방식을 확인하세요. 하락률은 0과 1 사이여야 합니다."); return;
  }
  const id = crypto.randomUUID();
  state.patterns.push({id, patternId: id, version: 1, active: true, name, kind, threshold, orderType});
  const saved = save(); event.target.reset(); $("pattern-kind").dispatchEvent(new Event("change")); render();
  if (saved) notice("패턴 초안을 저장했습니다. 종목에 연결해도 엔진에는 적용되지 않습니다.");
});
render();

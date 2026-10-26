"use strict";
(function expose(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else {
    root.CherryPulseSymbols = api;
    api.attach(document, fetch);
  }
})(globalThis, () => {
  function normalize(text) { return text.normalize("NFKC").replace(/\s+/g, "").toUpperCase(); }
  function validateDirectory(data) {
    if (data?.schemaVersion !== 1 || !Array.isArray(data.symbols) || data.symbols.length > 20000 || !Number.isFinite(Date.parse(data.fetchedAt))) throw new Error("INVALID_DIRECTORY");
    const codes = new Set();
    for (const row of data.symbols) {
      if (!Array.isArray(row) || row.length !== 4 || !/^\d{6}$/.test(row[0]) || typeof row[1] !== "string" || !row[1] || row[1].length > 100 || !["KOSPI", "KOSDAQ"].includes(row[2]) || !["주식", "ETF"].includes(row[3]) || codes.has(row[0])) throw new Error("INVALID_DIRECTORY");
      codes.add(row[0]);
    }
    return data;
  }
  function searchDirectory(data, query) {
    const q = normalize(query.trim());
    if (q.length < 2) return {matches: [], total: 0, exact: []};
    const rank = row => normalize(row[1]) === q || row[0] === q ? 0 : normalize(row[1]).startsWith(q) || row[0].startsWith(q) ? 1 : 2;
    const matches = data.symbols.filter(row => normalize(row[1]).includes(q) || row[0].includes(q)).sort((a, b) => rank(a) - rank(b) || a[1].localeCompare(b[1], "ko") || a[0].localeCompare(b[0]));
    return {matches: matches.slice(0, 20), total: matches.length, exact: matches.filter(row => rank(row) === 0)};
  }
  function attach(doc, fetcher, timers = {set: (callback, delay) => globalThis.setTimeout(callback, delay), clear: id => globalThis.clearTimeout(id)}) {
    const name = doc.getElementById("symbol-name"), code = doc.getElementById("symbol-input");
    const button = doc.getElementById("symbol-lookup-button"), status = doc.getElementById("symbol-lookup-status"), list = doc.getElementById("symbol-lookup-results");
    if (!name || !code || !button || !status || !list) return;
    let cached = null, pending = null, sequence = 0, timer, composing = false, selection = null;
    function invalidateSelection() {
      if (selection && name.value !== selection[1]) {
        if (code.value === selection[0]) code.value = "";
        selection = null;
      }
    }
    function choose(row) {
      sequence++; name.value = row[1]; code.value = row[0]; selection = row;
      list.replaceChildren(); status.textContent = `${row[1]} · ${row[0]} · ${row[2]} · ${row[3]} 선택 완료. 종목 추가를 누르세요.`;
    }
    async function directory() {
      if (cached) return cached;
      if (!pending) pending = (async () => {
        const response = await fetcher("/data/symbols.json", {cache: "no-cache", credentials: "omit", signal: AbortSignal.timeout(10000)});
        if (!response.ok) throw new Error("DIRECTORY_UNAVAILABLE");
        return validateDirectory(await response.json());
      })();
      try { cached = await pending; return cached; }
      finally { pending = null; }
    }
    async function lookup() {
      const id = ++sequence, query = name.value.trim();
      invalidateSelection(); list.replaceChildren();
      if (normalize(query).length < 2) { status.textContent = "종목명을 2자 이상 입력하세요. 예: 삼성전자, SK하이닉스"; return; }
      status.textContent = "종목코드를 검색하고 있습니다…";
      try {
        const data = await directory();
        if (id !== sequence || query !== name.value.trim()) return;
        const result = searchDirectory(data, query);
        if (!result.total) { status.textContent = "검색 결과가 없습니다. 숫자 6자리 KOSPI·KOSDAQ 주식/ETF만 지원합니다. 이름을 확인하거나 코드를 직접 입력하세요."; return; }
        const exact = result.exact.length === 1 ? result.exact[0] : null;
        if (exact) { code.value = exact[0]; selection = exact; }
        status.textContent = `${result.total}개 검색${result.total > 20 ? ' · 앞 20개 표시' : ''}${exact ? ' · 일치 종목 코드 자동 입력' : ' · 목록에서 선택하세요'} · 자료 수집 ${data.fetchedAt.slice(0, 10)}`;
        for (const row of result.matches) {
          const option = doc.createElement("button"); option.type = "button";
          option.textContent = `${row[1]} · ${row[0]} · ${row[2]} · ${row[3]}`;
          option.addEventListener("click", () => choose(row)); list.append(option);
        }
      } catch {
        if (id === sequence) status.textContent = "종목 목록을 불러오지 못했습니다. ‘종목명으로 코드 찾기’를 다시 누르거나 코드를 직접 입력하세요. 입력 내용은 유지됩니다.";
      }
    }
    function changed() {
      sequence++; invalidateSelection(); list.replaceChildren(); timers.clear(timer);
      if (!composing) timer = timers.set(lookup, 300);
    }
    name.addEventListener("input", changed);
    name.addEventListener("compositionstart", () => { composing = true; sequence++; timers.clear(timer); });
    name.addEventListener("compositionend", () => { composing = false; changed(); });
    code.addEventListener("input", () => { selection = null; sequence++; list.replaceChildren(); timers.clear(timer); });
    button.addEventListener("click", () => { timers.clear(timer); return lookup(); });
    doc.getElementById("symbol-form")?.addEventListener("reset", () => {
      sequence++; timers.clear(timer); selection = null; list.replaceChildren(); status.textContent = "종목명을 입력하면 코드를 검색합니다.";
    });
    return {lookup};
  }
  return {validateDirectory, searchDirectory, attach};
});

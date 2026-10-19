"use strict";

(function exposeBuyPreview(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.CherryPulseBuyPreview = api;
  }
})(globalThis, () => {
  const MAX_PRICE = 100000;

  function previewBuy(patterns, priceText) {
    const price = Number(String(priceText).trim());
    if (!Number.isFinite(price) || price <= 0) {
      return {ok: false, code: "PRICE_INVALID", hits: []};
    }
    const list = Array.isArray(patterns) ? patterns : [];
    const hits = [];
    for (const pattern of list) {
      if (!pattern || typeof pattern !== "object") continue;
      if (pattern.kind !== "BUY_PRICE_AT_OR_BELOW" || pattern.active === false) continue;
      const target = Number(pattern.threshold);
      if (!Number.isFinite(target) || target <= 0 || target > MAX_PRICE) continue;
      if (price <= target && typeof pattern.name === "string" && pattern.name) {
        hits.push(String(pattern.name).slice(0, 100));
      }
    }
    return {ok: true, code: "PREVIEW_ONLY", hits};
  }

  function positiveDecimal(value) {
    const text = String(value ?? "").trim();
    if (!/^(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(text)) return null;
    const number = Number(text);
    return Number.isFinite(number) && number > 0 ? number : null;
  }

  function previewSymbol(symbol, patterns, priceText, averageText) {
    const price = positiveDecimal(priceText);
    if (price === null) return {ok: false, message: "입력 가격은 0보다 큰 십진수로 입력하세요."};
    const list = Array.isArray(patterns) ? patterns : [];
    const evaluate = (id, buy) => {
      if (!id) return "미연결";
      const pattern = list.find((entry) => entry.id === id);
      if (!pattern || (pattern.kind === "BUY_PRICE_AT_OR_BELOW") !== buy) return "연결 오류";
      if (pattern.active === false) return "비활성 패턴 · 평가 제외";
      const threshold = positiveDecimal(pattern.threshold);
      if (threshold === null) return "기준값 오류";
      let matched;
      if (buy) {
        if (threshold > MAX_PRICE || pattern.orderType !== "LIMIT") return "매수 규칙 오류";
        matched = price <= threshold;
      } else if (pattern.kind === "PRICE_AT_OR_BELOW") {
        matched = price <= threshold;
      } else if (pattern.kind === "AVERAGE_COST_DROP") {
        if (threshold >= 1) return "기준값 오류";
        const average = positiveDecimal(averageText);
        if (average === null) return "평균 매수가 입력 필요";
        matched = price <= average * (1 - threshold);
      } else return "지원하지 않는 패턴";
      return matched ? "조건 충족 (입력값 기준)" : "조건 미충족 (입력값 기준)";
    };
    return {ok: true, buy: evaluate(symbol.buyPatternId, true), stop: evaluate(symbol.patternId, false),
      message: symbol.archived === true ? "보관 종목 · 가상 입력 미리보기 · 주문 없음" : "가상 입력 미리보기 · 실제 시세·체결·보호 상태 아님 · 주문 없음"};
  }

  return {previewBuy, previewSymbol, MAX_PRICE};
});

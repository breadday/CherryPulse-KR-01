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

  return {previewBuy, MAX_PRICE};
});

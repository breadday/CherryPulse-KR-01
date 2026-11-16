"use strict";

(function exposeManualOrderPreview(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.CherryPulseManualOrderPreview = api;
  }
})(globalThis, () => {
  function buildManualOrderPreview(input, symbols) {
    if (!input || typeof input !== "object") return {ok: false, code: "ORDER_INPUT_INVALID"};
    const symbolCode = String(input.symbol ?? "").trim();
    if (!/^\d{6}$/.test(symbolCode)) return {ok: false, code: "ORDER_SYMBOL_INVALID"};
    const symbol = (Array.isArray(symbols) ? symbols : []).find((item) =>
      item && item.code === symbolCode && item.archived !== true);
    if (!symbol) return {ok: false, code: "ORDER_SYMBOL_UNAVAILABLE"};

    const side = String(input.side ?? "");
    if (!["BUY", "SELL"].includes(side)) return {ok: false, code: "ORDER_SIDE_INVALID"};
    const quantityText = String(input.quantity ?? "").trim();
    const quantity = Number(quantityText);
    if (!/^[1-9]\d*$/.test(quantityText) || !Number.isSafeInteger(quantity)) {
      return {ok: false, code: "ORDER_QUANTITY_INVALID"};
    }
    const orderType = String(input.orderType ?? "");
    if (!["MARKET", "LIMIT"].includes(orderType)) return {ok: false, code: "ORDER_TYPE_INVALID"};

    let limitPrice = null;
    if (orderType === "LIMIT") {
      const priceText = String(input.limitPrice ?? "").trim();
      const price = Number(priceText);
      if (!/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(priceText) || !Number.isFinite(price) || price <= 0) {
        return {ok: false, code: "ORDER_PRICE_INVALID"};
      }
      limitPrice = priceText;
    }

    return {
      ok: true,
      review: {
        mode: "OFFLINE_PREVIEW",
        symbol: symbolCode,
        name: typeof symbol.name === "string" && symbol.name ? symbol.name.slice(0, 100) : symbolCode,
        side,
        quantity,
        orderType,
        limitPrice,
        orderSent: false,
        network: false,
      },
    };
  }

  function confirmManualOrderPreview(review) {
    if (!review || review.mode !== "OFFLINE_PREVIEW" || review.orderSent !== false || review.network !== false) {
      return {ok: false, code: "ORDER_PREVIEW_INVALID"};
    }
    return {
      ok: true,
      confirmation: {
        ...review,
        confirmed: true,
        confirmationMode: "OFFLINE_ONLY",
        orderSent: false,
        network: false,
      },
    };
  }

  return {buildManualOrderPreview, confirmManualOrderPreview};
});

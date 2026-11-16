"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const {buildManualOrderPreview} = require("./manual-order-preview.js");

test("builds an offline limit-order review from a registered active symbol", () => {
  const result = buildManualOrderPreview({
    symbol: "005930",
    side: "BUY",
    quantity: "2",
    orderType: "LIMIT",
    limitPrice: "70000",
  }, [{code: "005930", name: "삼성전자", archived: false}]);

  assert.deepEqual(result, {
    ok: true,
    review: {
      mode: "OFFLINE_PREVIEW",
      symbol: "005930",
      name: "삼성전자",
      side: "BUY",
      quantity: 2,
      orderType: "LIMIT",
      limitPrice: "70000",
      orderSent: false,
      network: false,
    },
  });
});

test("rejects unregistered or archived symbols and malformed order fields", () => {
  const symbols = [
    {code: "005930", name: "삼성전자", archived: false},
    {code: "000660", name: "SK하이닉스", archived: true},
  ];
  const base = {symbol: "005930", side: "BUY", quantity: "1", orderType: "LIMIT", limitPrice: "100"};
  assert.equal(buildManualOrderPreview({...base, symbol: "000001"}, symbols).code, "ORDER_SYMBOL_UNAVAILABLE");
  assert.equal(buildManualOrderPreview({...base, symbol: "000660"}, symbols).code, "ORDER_SYMBOL_UNAVAILABLE");
  for (const quantity of ["0", "-1", "1.5", "1e2", "9007199254740992"]) {
    assert.equal(buildManualOrderPreview({...base, quantity}, symbols).code, "ORDER_QUANTITY_INVALID");
  }
  assert.equal(buildManualOrderPreview({...base, side: "HOLD"}, symbols).code, "ORDER_SIDE_INVALID");
  for (const limitPrice of ["", "0", "-1", "NaN", "Infinity", "1e3"]) {
    assert.equal(buildManualOrderPreview({...base, limitPrice}, symbols).code, "ORDER_PRICE_INVALID");
  }
});

test("market preview has no price and local confirmation never sends an order", () => {
  const {confirmManualOrderPreview} = require("./manual-order-preview.js");
  const built = buildManualOrderPreview({
    symbol: "005930", side: "SELL", quantity: "3", orderType: "MARKET",
  }, [{code: "005930", name: "삼성전자"}]);
  assert.equal(built.ok, true);
  assert.equal(built.review.limitPrice, null);
  assert.deepEqual(confirmManualOrderPreview(built.review), {
    ok: true,
    confirmation: {
      ...built.review,
      confirmed: true,
      confirmationMode: "OFFLINE_ONLY",
      orderSent: false,
      network: false,
    },
  });
  assert.equal(confirmManualOrderPreview({}).ok, false);
});

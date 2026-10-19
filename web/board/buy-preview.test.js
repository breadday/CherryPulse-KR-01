"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const {previewBuy} = require("./buy-preview.js");

const patterns = [
  {name: "돌파", kind: "BUY_PRICE_AT_OR_BELOW", threshold: "50000", active: true},
  {name: "낮은목표", kind: "BUY_PRICE_AT_OR_BELOW", threshold: "40000", active: true},
  {name: "꺼짐", kind: "BUY_PRICE_AT_OR_BELOW", threshold: "60000", active: false},
  {name: "손절", kind: "PRICE_AT_OR_BELOW", threshold: "9000", active: true},
];

test("price at or below target lists active buy patterns only", () => {
  const result = previewBuy(patterns, "45000");
  assert.equal(result.ok, true);
  assert.deepEqual(result.hits, ["돌파"]);
});

test("invalid prices are rejected without hits", () => {
  assert.equal(previewBuy(patterns, "").ok, false);
  assert.equal(previewBuy(patterns, "-5").ok, false);
});

const {previewSymbol} = require("./buy-preview.js");
const linkedPatterns = [
  {id: "buy", name: "매수", kind: "BUY_PRICE_AT_OR_BELOW", threshold: "50000", orderType: "LIMIT"},
  {id: "stop", name: "손절", kind: "AVERAGE_COST_DROP", threshold: "0.03", orderType: "MARKET"},
];
test("linked preview checks inclusive boundaries and requires average for ratio stop", () => {
  const symbol = {buyPatternId: "buy", patternId: "stop"};
  assert.match(previewSymbol(symbol, linkedPatterns, "50000", "").buy, /^조건 충족/);
  assert.equal(previewSymbol(symbol, linkedPatterns, "50000", "").stop, "평균 매수가 입력 필요");
  assert.match(previewSymbol(symbol, linkedPatterns, "48500", "50000").stop, /^조건 충족/);
  assert.match(previewSymbol(symbol, linkedPatterns, "48501", "50000").stop, /^조건 미충족/);
  assert.match(previewSymbol(symbol, linkedPatterns, "50001", "50000").buy, /^조건 미충족/);
});
test("preview handles bad inputs, missing links and inactive patterns without invented prices", () => {
  for (const value of ["", "0", "-1", "NaN", "Infinity", "0x10"]) {
    assert.equal(previewSymbol({}, linkedPatterns, value, "").ok, false);
  }
  assert.equal(previewSymbol({}, linkedPatterns, "100", "").buy, "미연결");
  assert.equal(previewSymbol({buyPatternId: "missing"}, linkedPatterns, "100", "").buy, "연결 오류");
  assert.equal(previewSymbol({buyPatternId: "buy"}, [{...linkedPatterns[0], active: false}], "100", "").buy, "비활성 패턴 · 평가 제외");
  assert.match(previewSymbol({archived: true}, [], "100", "").message, /보관 종목/);
});
test("fixed stop preview evaluates price boundary", () => {
  const patterns = [{id: "fixed", kind: "PRICE_AT_OR_BELOW", threshold: "100"}];
  assert.match(previewSymbol({patternId: "fixed"}, patterns, "100", "").stop, /^조건 충족/);
  assert.match(previewSymbol({patternId: "fixed"}, patterns, "101", "").stop, /^조건 미충족/);
});

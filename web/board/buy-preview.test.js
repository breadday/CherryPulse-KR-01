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

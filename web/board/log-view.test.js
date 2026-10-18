"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const {LogViewError, parseLogText, describe} = require("./log-view.js");

test("parses probe submit and linkage lines without identifiers", () => {
  const text = [
    "not json line",
    JSON.stringify({
      mode: "PAPER",
      queries: [
        {api_id: "kt00018", complete: true, reason: "QUERY_COMPLETE_ONLY", pages: 1, observed_rows: 0},
      ],
    }),
    JSON.stringify({
      mode: "PAPER",
      order_submitted: true,
      acked: false,
      reason: "API_SUCCESS_UNCONFIRMED",
      broker_code: 20,
      broker_message: "모의투자 장종료 12345",
      symbol: "403870",
    }),
    JSON.stringify({
      mode: "PAPER",
      row_counts: {kt00007: 0, kt00009: 0},
      order_seen_in_multiple: false,
      fills_seen: false,
      reason: "LINKAGE_UNCONFIRMED",
    }),
  ].join("\n");
  const summary = parseLogText(text);
  assert.equal(summary.lines, 3);
  assert.equal(summary.probe.complete, true);
  assert.equal(summary.submit.submitted, true);
  assert.equal(summary.submit.acked, false);
  assert.equal(summary.submit.broker_code, 20);
  assert.match(summary.submit.broker_message, /<digits>/);
  assert.equal(summary.linkage.reason, "LINKAGE_UNCONFIRMED");
  assert.ok(!JSON.stringify(summary).includes("403870"));
  assert.ok(describe(summary).length > 0);
});

test("rejects empty text and non-json logs", () => {
  assert.throws(() => parseLogText(""), (error) => error instanceof LogViewError);
  assert.throws(() => parseLogText("hello\nworld"), (error) => error.code === "LOG_NO_JSON");
});

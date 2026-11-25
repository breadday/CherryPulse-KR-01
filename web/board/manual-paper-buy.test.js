const {test} = require("node:test");
const assert = require("node:assert/strict");
const {createHash} = require("node:crypto");
const {checkToday} = require("../../tools/check_paper_buy");
const {historyRow} = require("../lib/paper-orders");

test("follow the exact acknowledged number through order and fill history", async () => {
  const number = "000019";
  const claim = {status: "ACKED", qty: 3, order_digest: createHash("sha256").update(number).digest("hex")};
  for (const [executed, remaining, expected] of [[0, 3, "UNFILLED"], [1, 2, "PARTIALLY_FILLED"], [3, 0, "FILLED"]]) {
    const row = historyRow({ord_no: number, ord_qty: "3", cntr_qty: String(executed), oso_qty: String(remaining)}, true);
    assert.equal(await checkToday(claim, async () => ({orders: [], fills: [row]})), expected);
    assert.equal(await checkToday(claim, async () => ({orders: [], fills: [{...row, number: "19"}]})), "ACKED");
  }
});

test("ambiguous submissions and legacy claims require manual history inspection", async () => {
  for (const status of ["PENDING", "UNKNOWN", "ACKED"]) {
    assert.equal(await checkToday({status}, () => assert.fail("unexpected history call")), "CHECK_ORDER_HISTORY");
  }
});

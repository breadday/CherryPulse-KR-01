const {createHash} = require("node:crypto");
const {readFile} = require("node:fs/promises");
const path = require("node:path");
const {history} = require("../web/lib/paper-orders");

function statusFor(claim, tables) {
  const matches = [...tables.orders, ...tables.fills].filter(row =>
    row.number && createHash("sha256").update(row.number).digest("hex") === claim.order_digest);
  const states = new Set();
  for (const row of matches) {
    if (["취소", "거절"].includes(row.state)) return "CHECK_ORDER_HISTORY";
    if (row.qty !== claim.qty || row.executed === null || row.remaining === null ||
        row.executed < 0 || row.remaining < 0 || row.executed + row.remaining !== claim.qty) continue;
    if (row.executed === claim.qty) states.add("FILLED");
    else if (row.executed > 0) states.add("PARTIALLY_FILLED");
    else states.add("UNFILLED");
  }
  for (const state of ["FILLED", "PARTIALLY_FILLED", "UNFILLED"]) {
    if (states.has(state)) return state;
  }
  return "ACKED";
}

async function checkToday(claim, fetchHistory = history) {
  if (claim.status !== "ACKED" || !/^[a-f0-9]{64}$/.test(claim.order_digest)) {
    return "CHECK_ORDER_HISTORY";
  }
  return statusFor(claim, await fetchHistory());
}

async function main() {
  const day = new Intl.DateTimeFormat("sv-SE", {timeZone: "Asia/Seoul"}).format(new Date()).replaceAll("-", "");
  const file = path.join(__dirname, "..", "results", `paper-buy-${day}.json`);
  const claim = JSON.parse(await readFile(file, "utf8"));
  return checkToday(claim);
}

if (require.main === module) {
  main().catch(() => "CHECK_ORDER_HISTORY").then(status => {
    console.log(JSON.stringify({mode: "PAPER", status}));
    if (status === "CHECK_ORDER_HISTORY") process.exitCode = 1;
  });
}

module.exports = {checkToday};

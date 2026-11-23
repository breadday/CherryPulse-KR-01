const {request, token} = require("./paper");
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));

function integer(value) {
  if (value == null || value === "") return null;
  if (!/^[+-]?\d+$/.test(String(value).trim()) || !Number.isSafeInteger(Number(value)))
    throw new Error("INVALID_ACCOUNT_FIELD");
  return Number(value);
}

function holding(row) {
  const code = String(row.stk_cd || "").trim().replace(/^[AJQ](?=[A-Z0-9]{6}$)/, "");
  if (!/^[A-Z0-9]{6}$/.test(code)) throw new Error("INVALID_SYMBOL");
  return {code, name: row.stk_nm?.trim() || null, quantity: integer(row.rmnd_qty),
    average: integer(row.pur_pric), price: integer(row.cur_prc), value: integer(row.evlt_amt),
    profit: integer(row.evltv_prft), sellable: integer(row.trde_able_qty)};
}

async function readAccount(send = request, authenticate = token, wait = pause) {
  const authorization = "Bearer " + await authenticate();
  const call = (id, body, more = {}) => send("/api/dostk/acnt", body, {authorization, "api-id": id, ...more});
  const cash = (await call("kt00001", {qry_tp: "3"})).payload;
  if (cash.entr == null && cash.ord_alow_amt == null) throw new Error("MISSING_CASH");
  const holdings = [], seen = new Set();
  let more = {}, summary;
  for (let page = 0; page < 20; page++) {
    await wait(1050);
    const {payload, headers} = await call("kt00018", {qry_tp:"1", dmst_stex_tp:"KRX"}, more);
    summary ??= payload;
    if (!Array.isArray(payload.acnt_evlt_remn_indv_tot)) throw new Error("MISSING_HOLDINGS");
    holdings.push(...payload.acnt_evlt_remn_indv_tot.map(holding));
    if (headers.get("cont-yn") !== "Y") {
      return {deposit: integer(cash.entr), available: integer(cash.ord_alow_amt),
        assets: integer(summary.prsm_dpst_aset_amt), profit: integer(summary.tot_evlt_pl),
        holdings, fetchedAt: new Date().toISOString()};
    }
    const key = headers.get("next-key");
    if (!key || seen.has(key)) throw new Error("INCOMPLETE_HOLDINGS");
    seen.add(key);
    more = {"cont-yn":"Y", "next-key":key};
  }
  throw new Error("INCOMPLETE_HOLDINGS");
}

module.exports = {readAccount, integer};

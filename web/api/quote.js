const {post, token, configured} = require("../lib/paper");

module.exports = async function quote(req, res) {
  res.setHeader("Cache-Control", "no-store");
  if (req.method !== "GET") return res.status(405).end();
  const code = req.query.code;
  if (typeof code !== "string" || !/^\d{6}$/.test(code)) return res.status(400).end();
  if (!configured())
    return res.status(503).json({error: "QUOTE_NOT_CONFIGURED"});
  try {
    const data = await post("/api/dostk/chart", {stk_cd: code, tic_scope: "1", upd_stkpc_tp: "0"},
      {authorization: "Bearer " + await token(), "api-id": "ka10079"});
    const tick = data.stk_tic_chart_qry?.[0];
    const price = Math.abs(Number(tick?.cur_prc));
    const time = String(tick?.cntr_tm || "");
    if (data.stk_cd !== code || !Number.isSafeInteger(price) || price <= 0 || !/^\d{14}$/.test(time))
      return res.status(404).json({error: "NO_TRADE"});
    res.setHeader("Cache-Control", "public, s-maxage=10");
    return res.status(200).json({code, price, time});
  } catch {
    return res.status(502).json({error: "QUOTE_UNAVAILABLE"});
  }
};

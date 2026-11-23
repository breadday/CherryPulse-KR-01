const base = "https://mockapi.kiwoom.com";
const appKey = () => process.env.CHERRYPULSE_PAPER_APP_KEY || process.env.KIWOOM_APP_KEY;
const appSecret = () => process.env.CHERRYPULSE_PAPER_APP_SECRET || process.env.KIWOOM_APP_SECRET;
let tokenRequest;
let expires = 0;

async function post(path, body, headers = {}) {
  const response = await fetch(base + path, {
    method: "POST", redirect: "error", signal: AbortSignal.timeout(8000),
    headers: {"Content-Type": "application/json;charset=UTF-8", ...headers},
    body: JSON.stringify(body)
  });
  if (!response.ok) throw new Error("Quote service unavailable");
  const payload = await response.json();
  if (Number(payload.return_code) !== 0) throw new Error("Quote request declined");
  return payload;
}

async function token() {
  if (!tokenRequest || Date.now() >= expires) {
    expires = Date.now() + 60000;
    tokenRequest = post("/oauth2/token", {
      grant_type: "client_credentials", appkey: appKey(),
      secretkey: appSecret()
    }).then(data => {
      if (!data.token) throw new Error("Missing token");
      const expiry = String(data.expires_dt || "").match(/^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})$/);
      if (expiry) {
        const [, y, m, d, h, min, s] = expiry;
        expires = Date.parse(y+"-"+m+"-"+d+"T"+h+":"+min+":"+s+"+09:00") - 60000;
      }
      return data.token;
    }).catch(error => { tokenRequest = undefined; throw error; });
  }
  return tokenRequest;
}

module.exports = async function quote(req, res) {
  res.setHeader("Cache-Control", "no-store");
  if (req.method !== "GET") return res.status(405).end();
  const code = req.query.code;
  if (typeof code !== "string" || !/^\d{6}$/.test(code)) return res.status(400).end();
  if (!appKey() || !appSecret())
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

const base = "https://mockapi.kiwoom.com";
const appKey = () => process.env.CHERRYPULSE_PAPER_APP_KEY || process.env.KIWOOM_APP_KEY;
const appSecret = () => process.env.CHERRYPULSE_PAPER_APP_SECRET || process.env.KIWOOM_APP_SECRET;
let tokenRequest;
let expires = 0;

async function request(path, body, headers = {}) {
  const allowed = {
    "/oauth2/token": [undefined],
    "/api/dostk/acnt": ["kt00001","kt00018","kt00007","ka10076"],
    "/api/dostk/chart": ["ka10079"],
    "/api/dostk/stkinfo": ["ka10001"]
  };
  if (!Object.hasOwn(allowed,path) || !allowed[path].includes(headers["api-id"])) throw new Error("READ_ONLY_TRANSPORT");
  const response = await fetch(base + path, {
    method: "POST", redirect: "error", signal: AbortSignal.timeout(8000),
    headers: {"Content-Type": "application/json;charset=UTF-8", ...headers},
    body: JSON.stringify(body)
  });
  if (!response.ok) throw new Error("Quote service unavailable");
  const payload = await response.json();
  if (payload.return_code !== 0 && payload.return_code !== "0") throw new Error("Quote request declined");
  return {payload, headers: response.headers};
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

async function post(path, body, headers) {
  return (await request(path, body, headers)).payload;
}

module.exports = {post, request, token, configured: () => Boolean(appKey() && appSecret())};

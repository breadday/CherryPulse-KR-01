const {randomBytes,randomInt} = require("node:crypto");
const accessStatus = require("../lib/account-access");
const {cookieName,deviceId,sign,ticket} = require("../lib/account-device");
const endpoint = "https://qrrrnxmsbrkqueaabjdr.supabase.co/rest/v1/rpc/cp_account_device";
const publishable = "sb_publishable_AZ1sO52k9n3Uw1dZZYNaOQ_jwSO-Dxp";
module.exports = async function devicePin(req,res) {
  res.setHeader("Cache-Control","private, no-store");
  const fail = status => res.status(status).json({status});
  if (req.method!=="POST") return fail(405);
  if (req.headers.origin !== "https://"+req.headers.host ||
      !/^application\/json(?:;|$)/i.test(req.headers["content-type"] || "")) return fail(403);
  const {action,pin} = req.body || {};
  if (!["register","unlock","issue","pair"].includes(action) || typeof pin!=="string" || !/^\d{6}$/.test(pin)) return fail(422);
  const register = action==="register";
  const auth = accessStatus(req,true);
  if (auth===503 || !process.env.CHERRYPLUS_DEVICE_RPC_KEY) return fail(503);
  if (register && auth!==200) return fail(401);
  const enroll = register || action==="pair";
  const pairing = action==="issue" || action==="pair";
  const code = action==="issue" ? String(randomInt(1000000000000)).padStart(12,"0") : req.body.code;
  if (pairing && (typeof code!=="string" || !/^\d{12}$/.test(code))) return fail(422);
  const device = enroll ? randomBytes(32).toString("hex") : deviceId(req);
  if (!device) return fail(401);
  try {
    const args = {p_auth:process.env.CHERRYPLUS_DEVICE_RPC_KEY.trim(),p_device:sign("device",device),p_verifier:sign("pin",device,pin)};
    const response = await fetch(pairing ? endpoint.replace("cp_account_device","cp_pair_account_device") : endpoint,{method:"POST",redirect:"error",signal:AbortSignal.timeout(8000),
      headers:{apikey:publishable,"Content-Type":"application/json"},
      body:JSON.stringify(pairing ? {...args,p_issue:action==="issue",p_code:sign("code",code),p_pin:sign("pair-pin",code,pin)} : {...args,p_register:register})});
    if (!response.ok) return fail(503);
    const result = await response.json();
    if (result !== (action==="unlock" ? 200 : 201)) return fail([401,429].includes(result)?result:503);
    if (action==="issue") return res.status(200).json({code});
    if (enroll) res.setHeader("Set-Cookie",cookieName+"="+device+"; Secure; HttpOnly; SameSite=Strict; Path=/; Max-Age=7776000");
    return res.status(200).json({ticket:ticket(device)});
  } catch { return fail(503); }
};

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
    async function call(name,params) {
      const response = await fetch(endpoint.replace("cp_account_device",name),{method:"POST",redirect:"error",signal:AbortSignal.timeout(8000),
      headers:{apikey:publishable,"Content-Type":"application/json"},
      body:JSON.stringify(params)});
      if (!response.ok) throw Error("STORAGE_UNAVAILABLE");
      return response.json();
    }
    if (action!=="unlock") {
      const result = pairing ? await call("cp_pair_account_device",{...args,p_issue:action==="issue",p_code:sign("code",code),p_pin:sign("pair-pin",code,pin)})
        : await call("cp_account_device",{...args,p_register:true});
      if (result!==201) return fail([401,429].includes(result)?result:503);
      if (action==="issue") return res.status(200).json({code});
    }
    const owner = await call("cp_device_owner_session",args);
    if (!/^[a-f0-9]{64}$/.test(owner.sessionToken || "")) return fail([401,429].includes(owner.status)?owner.status:503);
    const attributes="; Secure; HttpOnly; SameSite=Strict; Path=/; Max-Age=";
    const cookies=["__Host-cp-reservations="+owner.sessionToken+attributes+"900"];
    cookies.push("__Host-cp-view="+ticket(device)+attributes+"900");
    if (enroll) cookies.push(cookieName+"="+device+attributes+"7776000");
    res.setHeader("Set-Cookie",cookies);
    return res.status(200).json({ticket:ticket(device)});
  } catch { return fail(503); }
};

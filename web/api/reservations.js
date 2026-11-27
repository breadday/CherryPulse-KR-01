const origin = "https://qrrrnxmsbrkqueaabjdr.supabase.co";
const publicKey = "sb_publishable_AZ1sO52k9n3Uw1dZZYNaOQ_jwSO-Dxp";
const cookie = "__Host-cp-reservations";
function sessionCookie(value, seconds) {
  return cookie+"="+value+"; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age="+seconds;
}
async function rpc(name,args) {
  const response = await fetch(origin+"/rest/v1/rpc/"+name, {
    method:"POST", headers:{apikey:publicKey,"Content-Type":"application/json"},
    body:JSON.stringify(args), redirect:"error",signal:AbortSignal.timeout(12000)
  });
  if (!response.ok) throw new Error("STORAGE_UNAVAILABLE");
  return response.json();
}
module.exports = async function reservations(req,res) {
  res.setHeader("Cache-Control","private, no-store");
  res.setHeader("Vary","Cookie");
  const fail = status => res.status(status).json({status});
  const actions = {GET:"list",POST:"create",PATCH:"update",DELETE:"cancel",PUT:"board-save"};
  let action = actions[req.method];
  if (!action) return fail(405);
  if (req.method !== "GET" && !/^application\/json(?:;|$)/i.test(req.headers["content-type"] || "")) return fail(415);
  const site = req.headers["sec-fetch-site"];
  if (site==="cross-site" || (req.method!=="GET" && site==="same-site")) return fail(403);
  if (req.method!=="GET" && req.headers.origin) {
    try {
      const source = new URL(req.headers.origin);
      if (source.host !== req.headers.host || !["https:","http:"].includes(source.protocol)) return fail(403);
    } catch { return fail(403); }
  }
  const token = (req.headers.cookie || "").split(/;\s*/).find(c=>c.startsWith(cookie+"="))?.slice(cookie.length+1);
  const body = req.body || {};
  try {
    if ((req.method==="GET" && req.query?.view==="pin-status") || (req.method==="POST" && body.action==="recover-pin")) {
      const reset = req.method==="POST";
      if (reset && (!/^[a-f0-9]{64}$/.test(body.code || "") || typeof body.pin!=="string" || !/^\d{4}(?:\d{2})?$/.test(body.pin))) return fail(422);
      const result = await rpc("cp_owner_pin_settings",{p_code:reset?body.code:null,p_pin:reset?body.pin:null});
      if (reset && result.status===403) return res.status(403).json({error:"RECOVERY_CODE_INVALID"});
      if (typeof result.configured!=="boolean") return fail([403,422].includes(result.status)?result.status:502);
      if (reset) res.setHeader("Set-Cookie",sessionCookie("",0));
      return res.status(200).json({configured:result.configured});
    }
    if (req.method==="POST" && body.action==="login") {
      if (typeof body.pin!=="string" || !/^\d{4}(?:\d{2})?$/.test(body.pin || "")) return fail(422);
      const result = await rpc("cp_pin_login",{p_pin:body.pin});
      if (!/^[a-f0-9]{64}$/.test(result.sessionToken || "")) return fail([401,429,503].includes(result.status)?result.status:502);
      res.setHeader("Set-Cookie",sessionCookie(result.sessionToken,43200));
      return res.status(200).json({ok:true});
    }
    if (!/^[a-f0-9]{64}$/.test(token || "")) return fail(401);
    if (req.method==="POST" && body.action==="logout") {
      await rpc("cp_pin_logout",{p_session:token});
      res.setHeader("Set-Cookie",[sessionCookie("",0),"__Host-cp-view=; Secure; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"]);
      return res.status(200).json({ok:true});
    }
    if (req.query?.view==="board" && ["GET","PUT"].includes(req.method)) {
      let result;
      if (req.method==="PUT") {
        if (!Number.isSafeInteger(body.expectedRevision) || body.expectedRevision<0 ||
            !/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i.test(body.requestKey || "")) return fail(422);
        try {require("../board/board-backup").parseBoardBackup(JSON.stringify(body.snapshot));}
        catch {return fail(422);}
        result=await rpc("cp_pin_save_board",{p_session:token,p_expected_revision:body.expectedRevision,p_request_key:body.requestKey,p_snapshot:body.snapshot});
      } else result=await rpc("cp_pin_load_board",{p_session:token});
      if (result.status) return res.status(result.status).json({error:{code:result.code}});
      return res.status(200).json(result);
    }
    if (req.method==="PUT") return fail(405);
    if (action!=="list" && !/^[\da-f]{8}(-[\da-f]{4}){3}-[\da-f]{12}$/i.test(body.id || "")) return fail(422);
    if (body.approvePaper===true) {
      const {validTicket}=require("../lib/account-device");
      const {cookie,claimRpc}=require("../lib/manual-paper-order");
      if (!["create","update"].includes(action) || req.headers.origin!=="https://"+req.headers.host ||
          !validTicket(req,cookie(req,"__Host-cp-view") || "")) return fail(403);
      const saved=await claimRpc(req,"cp_save_scheduled_paper",{p_action:action,p_id:body.id,
        p_version:body.version??null,p_details:body.details});
      return saved.status?fail(saved.status):res.status(200).json(saved);
    }
    const result = await rpc("cp_reservations",{p_session:token,p_action:action,p_id:body.id??null,
      p_version:body.version??null,p_details:body.details??null});
    if (result.status) return fail([401,404,409,422].includes(result.status)?result.status:502);
    return res.status(200).json(result);
  } catch {return fail(503);}
};

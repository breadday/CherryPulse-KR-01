const {createHmac, timingSafeEqual} = require("node:crypto");
const cookieName = "__Host-cp-account-device";
function deviceId(req) {
  const item = (req.headers.cookie || "").split(/;\s*/).find(value => value.startsWith(cookieName+"="));
  const value = item?.slice(cookieName.length+1);
  return /^[a-f0-9]{64}$/.test(value || "") ? value : null;
}
function sign(purpose, ...parts) {
  return createHmac("sha256", process.env.CHERRYPLUS_DEVICE_RPC_KEY.trim())
    .update(JSON.stringify([purpose,process.env.CHERRYPLUS_ACCOUNT_VIEW_KEY,...parts])).digest("hex");
}
function ticket(device, now=Date.now()) {
  const expiry = String(now + 15*60*1000);
  return "device."+expiry+"."+sign("session",device,expiry);
}
function validTicket(req, value) {
  const device = deviceId(req);
  if (!device || !process.env.CHERRYPLUS_DEVICE_RPC_KEY) return false;
  const match = /^device\.(\d{13})\.([a-f0-9]{64})$/.exec(value);
  return Boolean(match && Number(match[1]) > Date.now() &&
    timingSafeEqual(Buffer.from(match[2],"hex"), Buffer.from(sign("session",device,match[1]),"hex")));
}
module.exports = {cookieName,deviceId,sign,ticket,validTicket};

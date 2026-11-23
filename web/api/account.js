const accessStatus=require("../lib/account-access");
const {readAccount}=require("../lib/account");
module.exports = async function account(req, res) {
  res.setHeader("Cache-Control", "private, no-store");
  res.setHeader("Vary", "Authorization");
  if (req.method !== "GET") return res.status(405).end();
  const status=accessStatus(req);
  if (status!==200) return res.status(status).json({error:status===401?"VIEWER_REQUIRED":"SETUP_REQUIRED"});
  try {
    return res.status(200).json(await readAccount());
  } catch (error) {
    const timeout = ["AbortError", "TimeoutError"].includes(error.name);
    return res.status(timeout ? 504 : 502).json({error:timeout ? "TIMEOUT" : "ACCOUNT_UNAVAILABLE"});
  }
};

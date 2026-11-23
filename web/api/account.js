const {createHash, timingSafeEqual} = require("node:crypto");
const {configured} = require("../lib/paper");
const {readAccount} = require("../lib/account");
const digest = value => createHash("sha256").update(value).digest();

module.exports = async function account(req, res) {
  res.setHeader("Cache-Control", "private, no-store");
  res.setHeader("Vary", "Authorization");
  if (req.method !== "GET") return res.status(405).end();
  const key = process.env.CHERRYPLUS_ACCOUNT_VIEW_KEY;
  if (!key || key.length < 32 || !configured()) return res.status(503).json({error:"SETUP_REQUIRED"});
  const supplied = (req.headers.authorization || "").match(/^Bearer (\S+)$/)?.[1];
  if (!supplied || !timingSafeEqual(digest(supplied), digest(key))) return res.status(401).json({error:"VIEWER_REQUIRED"});
  try {
    return res.status(200).json(await readAccount());
  } catch (error) {
    const timeout = ["AbortError", "TimeoutError"].includes(error.name);
    return res.status(timeout ? 504 : 502).json({error:timeout ? "TIMEOUT" : "ACCOUNT_UNAVAILABLE"});
  }
};

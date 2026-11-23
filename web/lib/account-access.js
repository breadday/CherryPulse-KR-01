const {createHash, timingSafeEqual} = require("node:crypto");
const {configured} = require("./paper");
const digest = value => createHash("sha256").update(value).digest();

module.exports = function accessStatus(req) {
  const key = process.env.CHERRYPLUS_ACCOUNT_VIEW_KEY;
  if (!key || key.length < 32 || !configured()) return 503;
  const supplied = (req.headers.authorization || "").match(/^Bearer (\S+)$/)?.[1];
  if (!supplied || !timingSafeEqual(digest(supplied), digest(key))) return 401;
  return 200;
};

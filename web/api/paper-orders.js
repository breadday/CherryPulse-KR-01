const accessStatus = require("../lib/account-access");
const {prepare,history} = require("../lib/paper-orders");
module.exports = async function paperOrders(req,res) {
  res.setHeader("Cache-Control","private, no-store");
  res.setHeader("Vary","Authorization");
  if (req.method!=="GET" && !(req.method==="POST" && req.query?.action==="prepare")) return res.status(405).end();
  const status=accessStatus(req);
  if (status!==200) return res.status(status).json({error:"모의계좌 열람 권한이 필요합니다."});
  try {
    return res.status(200).json(req.method==="GET"?await history():await prepare(req.body || {}));
  } catch (e) {
    return res.status(e instanceof RangeError?422:502).json({error:e instanceof RangeError?e.message:"조회 결과를 확인할 수 없습니다."});
  }
};

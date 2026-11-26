const accessStatus = require("../lib/account-access");
const {prepare,history} = require("../lib/paper-orders");
const manualOrder = require("../lib/manual-paper-order");
module.exports = async function paperOrders(req,res) {
  res.setHeader("Cache-Control","private, no-store");
  res.setHeader("Vary","Authorization");
  if (req.method!=="GET" && !(req.method==="POST" && ["prepare","manual-sell","manual-buy"].includes(req.query?.action))) return res.status(405).end();
  const status=accessStatus(req);
  if (status!==200) return res.status(status).json({error:"모의계좌 열람 권한이 필요합니다."});
  try {
    if (req.method==="GET") return res.status(200).json(await history());
    const input=req.body || {};
    if (req.query.action!=="prepare") {
      const side=req.query.action==="manual-buy" ? "매수" : "매도";
      if (input.side!==side) return res.status(422).json({error:"주문 방향을 다시 확인하세요."});
      const result=await manualOrder.submit(req,input);
      return res.status(result.status).json(result.body);
    }
    return res.status(200).json({...await prepare(input),confirmation:input.side==="매수" && input.manualBuy!==true ? null : manualOrder.confirmation(req,input)});
  } catch (e) {
    return res.status(e instanceof RangeError?422:502).json({error:e instanceof RangeError?e.message:"조회 결과를 확인할 수 없습니다."});
  }
};

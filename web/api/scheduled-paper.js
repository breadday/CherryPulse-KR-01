const {claimRpc,sendOrder}=require("../lib/manual-paper-order");
const {prepare}=require("../lib/paper-orders");
const {token}=require("../lib/paper");

module.exports=async function scheduledPaper(req,res) {
  res.setHeader("Cache-Control","no-store");
  if (req.method!=="POST") return res.status(405).end();
  const key=req.body?.key;
  if (typeof key!=="string" || !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(key)) return res.status(400).end();
  const rpc=(action,data={})=>claimRpc(req,"cp_scheduled_paper_worker",{
    p_session:undefined,p_key:key,p_action:action,p_data:data
  });
  try {
    const record=await rpc("preview");
    if (!record.details) return res.status(409).end();
    const {apiId,body}=await prepare(record.details);
    const bearer=await token();
    const claim=await rpc("claim");
    if (!claim.details || !(Date.parse(claim.deadline)>Date.now())) return res.status(409).end();
    const timing={};
    const response=await sendOrder(apiId,body,bearer,timing);
    const state=response.status===200?"accepted":response.rejected?"rejected":"unknown";
    const saved=await rpc("response",{...timing,state,number:response.body.number});
    return res.status(saved.ok?200:502).end();
  } catch { return res.status(503).end(); }
};

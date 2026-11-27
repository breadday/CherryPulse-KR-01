const {randomUUID} = require("node:crypto");
const {claimRpc,cookie,sendOrder} = require("./manual-paper-order");
const {validTicket,deviceId,sign} = require("./account-device");
const {request,token} = require("./paper");

const day = () => new Intl.DateTimeFormat("sv-SE",{timeZone:"Asia/Seoul"}).format(new Date());
const fail = (status,error) => ({status,body:{error}});
function signedRow(req,row,tradeDay) {
  return sign("paper-order-change",deviceId(req),cookie(req,"__Host-cp-reservations"),tradeDay,row.number,row.code,row.price,row.remaining);
}
function review(req,row) {
  if (!validTicket(req,cookie(req,"__Host-cp-view") || "") || !cookie(req,"__Host-cp-reservations") ||
      !["미체결","부분체결","접수"].includes(row.state) || !row.number || !/^\d{6}$/.test(row.code) || !(row.remaining>0)) return null;
  const tradeDay=day();
  return {tradeDay,signature:signedRow(req,row,tradeDay)};
}
async function change(req,input) {
  const {action,number,code,remaining,price,newPrice,approval}=input;
  if (req.headers.origin!=="https://"+req.headers.host || !/^application\/json(?:;|$)/i.test(req.headers["content-type"] || "") ||
      !validTicket(req,cookie(req,"__Host-cp-view") || "")) return fail(403,"등록 기기 PIN으로 로그인하세요.");
  if (!approval || approval.tradeDay!==day() || approval.signature!==signedRow(req,input,approval.tradeDay))
    return fail(409,"오늘의 주문·체결 내역을 다시 조회하세요.");
  if (!["amend","cancel"].includes(action) || !Number.isSafeInteger(remaining) || remaining<=0 ||
      (action==="amend" && (!Number.isSafeInteger(newPrice) || newPrice<=0 || newPrice===price || !(price>0))))
    return fail(422,"새 지정가와 잔량을 확인하세요.");
  const bearer=await token();
  const headers={"api-id":"ka10075",authorization:"Bearer "+bearer};
  const params={all_stk_tp:"1",trde_tp:"0",stk_cd:code,stex_tp:"1"};
  let open;
  const seen=new Set();
  for (;;) {
    const page=await request("/api/dostk/acnt",params,headers);
    open=page.payload.oso.find(row=>String(row.ord_no).trim().replace(/^0+/,"")===number.replace(/^0+/,"") &&
      String(row.stk_cd).trim().replace(/^A/,"")===code);
    if (open || page.headers.get("cont-yn")!=="Y") break;
    const next=page.headers.get("next-key");
    if (!next || seen.has(next) || seen.size>=19) throw Error("INCOMPLETE_OPEN_ORDERS");
    seen.add(next);headers["next-key"]=next;headers["cont-yn"]="Y";
    await new Promise(resolve=>setTimeout(resolve,1050));
  }
  if (!open || Number(open.oso_qty)!==remaining || Number(open.ord_pric)!==price)
    return fail(409,"미체결 주문의 가격 또는 잔량이 바뀌었습니다. 다시 조회하세요.");
  const args={p_key:sign("order-change-key",approval.tradeDay,number.replace(/^0+/,"")),p_request:randomUUID(),p_rejected:false};
  const claim=await claimRpc(req,"cp_claim_order_change",args);
  if (claim!==201) return fail(claim===409?409:403,claim===409?"이 원주문의 변경 요청이 이미 기록됐습니다. 주문내역을 다시 조회하세요.":"PIN으로 다시 로그인하세요.");
  const body={dmst_stex_tp:"KRX",orig_ord_no:number,stk_cd:code};
  if (action==="amend") Object.assign(body,{mdfy_qty:String(remaining),mdfy_uv:String(newPrice),mdfy_cond_uv:""});
  else body.cncl_qty=String(remaining);
  const result=await sendOrder(action==="amend"?"kt10002":"kt10003",body,bearer);
  if (result.rejected) await claimRpc(req,"cp_claim_order_change",{...args,p_rejected:true});
  return result;
}
module.exports={review,change};

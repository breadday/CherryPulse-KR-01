const {deviceId,sign,validTicket}=require("./account-device");
const {cookie,claimRpc,sendOrder}=require("./manual-paper-order");
const {prepare,history}=require("./paper-orders");
const {token}=require("./paper");

function orderTime(day,time) {
  const match=/^(\d{2}):?(\d{2}):?(\d{2})$/.exec(time || "");
  if (!match || +match[1]>23 || +match[2]>59 || +match[3]>59) return null;
  return day+"T"+match.slice(1).join(":")+"+09:00";
}
function reconcile(record,tables,selected,now=new Date()) {
  const d=record.details;
  // Both history endpoints return the current Korean trading day's records.
  if (new Date(now.getTime()+9*3600000).toISOString().slice(0,10)!==d.date) return {};
  const rows=[...tables.orders,...tables.fills].filter(r=>r.code===d.code && r.number);
  const original=r=>!r.originalNumber && r.qty===d.qty && r.price===d.price &&
    String(r.side || "").replace(/^[+-]/,"").trim()===d.side;
  const plausible=rows.filter(r=>original(r) && orderTime(d.date,r.time) &&
    Math.floor(Date.parse(record.startedAt)/1000)<=Date.parse(orderTime(d.date,r.time))/1000);
  if (!record.number && !plausible.some(r=>r.number===selected)) {
    return {candidates:[...new Map(plausible.map(r=>[r.number,{number:r.number,time:r.time}])).values()]};
  }
  const number=record.number || selected;
  const receipt=rows.find(r=>r.number===number && original(r) && ["접수","미체결"].includes(r.state));
  const acceptedAt=orderTime(d.date,receipt?.time);
  const states={"접수":"accepted","미체결":"unfilled","부분체결":"partial","완료":"filled","거절":"rejected"};
  // Follow only explicit correction links. A cancellation with zero balance is not a fill.
  const linked=new Set([number]);
  for (let previous=0;previous!==linked.size;) {
    previous=linked.size;
    for (const r of rows) if (linked.has(r.originalNumber) && String(r.side).includes(d.side+"정정")) linked.add(r.number);
  }
  const matches=rows.filter(r=>linked.has(r.number) && states[r.state] && !String(r.side).includes("취소") &&
    (["접수","거절"].includes(r.state) || (Number.isSafeInteger(r.executed) && Number.isSafeInteger(r.remaining) &&
      r.executed>=0 && r.remaining>=0 && r.executed+r.remaining===d.qty)));
  matches.sort((a,b)=>(b.executed??-1)-(a.executed??-1) || Number(b.state==="미체결")-Number(a.state==="미체결"));
  const best=matches[0];
  if (!best) return {};
  const quantities=["미체결","부분체결","완료"].includes(best.state);
  return {observation:{number,state:states[best.state],acceptedAt,executed:quantities?best.executed:null,remaining:quantities?best.remaining:null}};
}
async function reservationOrder(req,input,action) {
  const status=(n,message)=>({status:n,body:{error:message}});
  const result=body=>({status:200,body});
  const session=cookie(req,"__Host-cp-reservations");
  if (!validTicket(req,cookie(req,"__Host-cp-view") || "") || !/^[a-f0-9]{64}$/.test(session || "") ||
      req.headers.origin!=="https://"+req.headers.host || !/^application\/json(?:;|$)/i.test(req.headers["content-type"] || ""))
    return status(403,"등록 기기 PIN으로 로그인하세요.");
  if (!/^[\da-f]{8}(-[\da-f]{4}){3}-[\da-f]{12}$/i.test(input.id || "") || !Number.isSafeInteger(input.version) || input.version<1)
    return status(422,"예약과 버전을 확인하세요.");
  const rpc=(operation,data={})=>claimRpc(req,"cp_reservation_paper",{p_id:input.id,p_version:input.version,p_action:operation,p_data:data});
  const startedAt=new Date().toISOString();
  const record=await rpc(action==="reservation-refresh"?"inspect":"preview");
  if (record.status) return status(record.status,"최신 예약과 전송 기록을 확인하세요.");
  if (action==="reservation-refresh") {
    const date=new Date(Date.now()+9*3600000).toISOString().slice(0,10);
    if (record.details.date!==date) return status(409,"해당 거래일 주문내역을 확인하세요.");
    const match=reconcile(record,await history(),input.number);
    if (match.candidates) return result({candidates:match.candidates});
    if (!match.observation) return result({ok:true,matched:false});
    const saved=await rpc("observe",match.observation);
    return saved.status?status(saved.status,"주문 연결을 확인하세요."):result({ok:true,matched:true});
  }
  const proof=expiry=>sign("reservation-paper",deviceId(req),session,input.id,input.version,expiry);
  if (action==="reservation-preview") {
    await prepare(record.details);
    const expiry=Date.now()+120000;
    return result({confirmation:{expiry,signature:proof(expiry)}});
  }
  const approval=input.confirmation;
  if (!Number.isSafeInteger(approval?.expiry) || approval.expiry<=Date.now() || approval.signature!==proof(approval.expiry))
    return status(409,"선택한 예약을 다시 사전검증하세요.");
  const {apiId,body}=await prepare(record.details);
  const bearer=await token();
  const claim=await rpc("claim",{startedAt});
  if (claim.status) return status(claim.status,"이미 처리했거나 예약 시각이 지났습니다.");
  const timing={};
  // sendOrder starts fetch synchronously. Persist that timestamp while the broker is responding.
  const [response]=await Promise.all([sendOrder(apiId,body,bearer,timing),
    rpc("dispatch",{sentAt:timing.sentAt}).catch(()=>null)]);
  const state=response.status===200?"accepted":response.rejected?"rejected":"unknown";
  const saved=await rpc("response",{...timing,state,number:response.body.number});
  if (saved.status) return status(502,"접수 확인이 필요합니다. 주문내역을 조회하세요.");
  return response;
}
module.exports={reservationOrder,reconcile};

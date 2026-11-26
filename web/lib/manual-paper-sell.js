const {deviceId, sign, validTicket} = require("./account-device");
const {prepare} = require("./paper-orders");
const {token} = require("./paper");

function cookie(req, name) {
  return (req.headers.cookie || "").split(/;\s*/).find(item => item.startsWith(name+"="))?.slice(name.length+1);
}
function eligible(req, input) {
  return input.side === "매도" && input.type === "지정가" && input.schedule === "now" &&
    validTicket(req,cookie(req,"__Host-cp-view") || "") &&
    /^[a-f0-9]{64}$/.test(cookie(req,"__Host-cp-reservations") || "");
}
function proof(req, input, expiry) {
  return sign("manual-paper-sell",deviceId(req),cookie(req,"__Host-cp-reservations"),input.code,input.qty,input.price,expiry);
}
function confirmation(req,input) {
  if (!eligible(req,input)) return null;
  const expiry = Date.now()+120000;
  return {expiry, signature:proof(req,input,expiry)};
}
async function submit(req, input) {
  const fail = (status,error) => ({status,body:{error}});
  if (!eligible(req,input) || req.headers.origin !== "https://"+req.headers.host ||
      !/^application\/json(?:;|$)/i.test(req.headers["content-type"] || "")) return fail(403,"등록 기기 PIN으로 로그인하세요.");
  const approval=input.confirmation;
  if (!Number.isSafeInteger(approval?.expiry) || approval.expiry <= Date.now() ||
      approval.signature !== proof(req,input,approval.expiry)) return fail(409,"주문 조건을 다시 사전검증하세요.");
  const {body} = await prepare(input);
  const bearer = await token();
  const claim = await fetch("https://qrrrnxmsbrkqueaabjdr.supabase.co/rest/v1/rpc/cp_claim_manual_paper_sell",{
    method:"POST",redirect:"error",signal:AbortSignal.timeout(8000),
    headers:{apikey:"sb_publishable_AZ1sO52k9n3Uw1dZZYNaOQ_jwSO-Dxp","Content-Type":"application/json"},
    body:JSON.stringify({p_session:cookie(req,"__Host-cp-reservations"),p_auth:process.env.CHERRYPLUS_DEVICE_RPC_KEY.trim(),
      p_symbol:input.code,p_qty:input.qty,p_price:input.price})
  });
  if (!claim.ok) return fail(503,"전송 기록을 확인할 수 없습니다.");
  const result = await claim.json();
  if (result === 409) return fail(409,"오늘 같은 조건의 전송 기록이 있습니다. 주문·체결 내역을 확인하세요.");
  if (result !== 201) return fail(403,"전송 권한을 확인할 수 없습니다. PIN으로 다시 로그인하세요.");
  try {
    const response = await fetch("https://mockapi.kiwoom.com/api/dostk/ordr",{
      method:"POST",redirect:"error",signal:AbortSignal.timeout(8000),
      headers:{"Content-Type":"application/json;charset=UTF-8","api-id":"kt10001",authorization:"Bearer "+bearer},
      body:JSON.stringify(body)
    });
    const data = await response.json();
    if (response.ok && [0,"0"].includes(data.return_code) && typeof data.ord_no==="string" &&
        /^\d+$/.test(data.ord_no.trim()) && /[1-9]/.test(data.ord_no)) {
      return {status:200,body:{number:data.ord_no.trim()}};
    }
    if (response.ok && /^-?[1-9]\d*$/.test(String(data.return_code))) return fail(422,"키움이 모의매도를 거절했습니다. 응답 코드 "+data.return_code);
  } catch { /* The claim remains durable if the broker response is lost. */ }
  return fail(502,"접수 여부가 불명확합니다. 주문·체결 내역에서 확인하세요.");
}
module.exports = {confirmation,submit};

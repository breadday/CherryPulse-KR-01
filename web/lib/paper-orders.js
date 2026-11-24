const {request,token} = require("./paper");
const {readAccount,integer} = require("./account");
const pause = ms=>new Promise(resolve=>setTimeout(resolve,ms));
const positive = n=>Number.isSafeInteger(n) && n>0 && n<=999999999999;
function orderBody(input) {
  const {code,side,type,price,qty}=input;
  if (typeof code!=="string" || !/^\d{6}$/.test(code) || !positive(qty) ||
      !["매수","매도"].includes(side) || !["지정가","시장가"].includes(type) ||
      (type==="지정가" ? !positive(price) : price!==null)) throw new RangeError("주문 입력을 확인하세요.");
  return {apiId:side==="매수"?"kt10000":"kt10001",body:{dmst_stex_tp:"KRX",stk_cd:code,
    ord_qty:String(qty),ord_uv:type==="시장가"?"":String(price),trde_tp:type==="시장가"?"3":"0",cond_uv:""}};
}
async function prepare(input) {
  const contract=orderBody(input);
  const account=await readAccount();
  if (input.side==="매수") {
    let ceiling=input.price;
    if (input.type==="시장가") {
      const {payload}=await request("/api/dostk/stkinfo",{stk_cd:input.code},{authorization:"Bearer "+await token(),"api-id":"ka10001"});
      ceiling=payload.stk_cd===input.code ? Math.abs(integer(payload.upl_pric) || 0) : 0;
    }
    const cost=ceiling*input.qty;
    if (!positive(ceiling) || !Number.isSafeInteger(cost) || account.available===null || account.available<cost)
      throw new RangeError("주문가능금액 또는 매수 가격 한도를 확인하세요.");
  } else {
    const positions=account.holdings.filter(row=>row.code===input.code);
    if (positions.length!==1 || positions[0].sellable===null || positions[0].sellable<input.qty)
      throw new RangeError("매도가능수량을 확인하세요.");
  }
  return {apiId:contract.apiId,body:contract.body,checkedAt:account.fetchedAt,transmitted:false};
}
function orderNumber(value) {
  const number = typeof value === "string" ? value.trim() : "";
  return /^\d+$/.test(number) && /[1-9]/.test(number) ? number : null;
}
function historyRow(row,fill) {
  const qty=integer(row.ord_qty), executed=integer(row.cntr_qty),remaining=integer(fill?row.oso_qty:row.ord_remnq);
  const raw=String(row.ord_stt || row.acpt_tp || "").trim();
  let state="결과 불명";
  const number=orderNumber(row.ord_no);
  if (["거부","거절"].includes(raw)) state="거절";
  else if (number) {
    if (["취소","취소완료"].includes(raw)) state="취소";
    else if (executed>0 && remaining===0 && executed===qty) state="완료";
    else if (executed>0 && remaining>0) state="부분체결";
    else if (executed>0 && fill) state="체결 확인";
    else if (remaining>0 && executed===0) state="미체결";
    else if (raw==="접수") state="접수";
  }
  return {number,originalNumber:orderNumber(fill ? row.orig_ord_no : row.ori_ord),
    time:row.ord_tm || null,name:row.stk_nm || row.stk_cd || null,
    side:row.io_tp_nm || null,qty,executed,remaining,price:integer(fill?row.ord_pric:row.ord_uv),
    fillPrice:integer(fill?row.cntr_pric:row.cntr_uv),state};
}
async function history() {
  const authorization="Bearer "+await token(), result={};
  const specs=[
    ["orders","kt00007","acnt_ord_cntr_prps_dtl",{qry_tp:"1",stk_bond_tp:"0",sell_tp:"0",dmst_stex_tp:"KRX"}],
    ["fills","ka10076","cntr",{qry_tp:"0",sell_tp:"0",stex_tp:"1"}]];
  for (const [section,id,key,params] of specs) {
    const rows=[], seen=new Set(); let more={};
    for (;;) {
      if (section==="fills" || seen.size) await pause(1050);
      const {payload,headers}=await request("/api/dostk/acnt",params,{authorization,"api-id":id,...more});
      if (!Array.isArray(payload[key])) throw Error("HISTORY_INVALID");
      rows.push(...payload[key].map(row=>historyRow(row,section==="fills")));
      if (headers.get("cont-yn")!=="Y") break;
      const next=headers.get("next-key");
      if (!next || seen.has(next) || seen.size>=19) throw Error("HISTORY_INCOMPLETE");
      seen.add(next);more={"cont-yn":"Y","next-key":next};
    }
    result[section]=rows;
  }
  return result;
}
module.exports={orderBody,prepare,history,historyRow};

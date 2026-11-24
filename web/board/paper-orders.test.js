const {test}=require("node:test");
const assert=require("node:assert/strict");
const {orderBody,historyRow}=require("../lib/paper-orders");
const {request}=require("../lib/paper");
test("KRX buy/sell contracts and read-only transport",async t=>{
  const net=t.mock.method(global,"fetch");
  for(const side of ["매수","매도"]) for(const price of [null,70000]){
    const {apiId,body}=orderBody({side,code:"005930",qty:2,type:price?"지정가":"시장가",price});
    assert.equal(apiId,side==="매수"?"kt10000":"kt10001");
    assert.equal(body.ord_uv,price?"70000":"");
    assert.equal(body.trde_tp,price?"0":"3");
    await assert.rejects(request("/api/dostk/ordr",body,{"api-id":apiId}),/READ_ONLY/);
  }
  assert.equal(net.mock.callCount(),0);
});
test("unknown responses never imply acceptance; explicit quantities distinguish fills",()=>{
  const row={ord_no:"001",ord_qty:"3",cntr_qty:"1",ord_remnq:"2"};
  assert.equal(historyRow(row,false).state,"부분체결");
  assert.equal(historyRow({...row,ord_no:""},false).state,"결과 불명");
  assert.equal(historyRow({...row,cntr_qty:"3",ord_remnq:"0"},false).state,"완료");
  assert.equal(historyRow({...row,acpt_tp:"거부"},false).state,"거절");
});
test("broker rejection and original order numbers survive history normalization", () => {
  const rejected = historyRow({ord_no:"0000", acpt_tp:"거절"}, false);
  assert.equal(rejected.state, "거절");
  assert.equal(rejected.number, null);
  for (const fill of [true, false]) {
    const row = historyRow({ord_no:" 000123 ", [fill ? "orig_ord_no" : "ori_ord"]:"000099"}, fill);
    assert.equal(row.number, "000123");
    assert.equal(row.originalNumber, "000099");
  }
});

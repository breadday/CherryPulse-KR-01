(() => {
  const el=id=>document.getElementById(id);
  async function status() {
    if (location.hash!=="#ops") return;
    try {
      const r=await fetch("/api/reservations?view=pin-status",{cache:"no-store"});
      const data=await r.json();
      if (!r.ok || typeof data.configured!=="boolean") throw Error();
      el("pin-state").textContent=data.configured?"PIN 설정됨 · 소유자 확인 후 변경할 수 있습니다.":"PIN 미설정 · 소유자 확인 후 최초 설정하세요.";
    } catch {el("pin-state").textContent="PIN 설정 상태 조회 실패";}
  }
  addEventListener("hashchange",status);
  status();
  el("pin-recovery").onsubmit=async event=>{
    event.preventDefault();
    const pin=el("new-pin").value;
    if (pin!==el("repeat-pin").value) {el("pin-result").textContent="새 PIN 두 값이 다릅니다.";return;}
    const code=el("owner-code").value.trim();
    const form=event.currentTarget;
    const submit=form.querySelector("button");
    if (submit.disabled) return;
    submit.disabled=true;
    el("pin-result").textContent="저장 중…";
    try {
      const r=await fetch("/api/reservations",{method:"POST",headers:{"Content-Type":"application/json"},
        cache:"no-store",redirect:"error",body:JSON.stringify({action:"recover-pin",code,pin})});
      if (!r.ok) {
        const body=await r.json().catch(()=>({}));
        const messages={
          403:body.error==="RECOVERY_CODE_INVALID"?"복구 코드가 일치하지 않거나 만료·사용됐습니다. 가장 최근 코드를 확인하세요.":"요청 출처를 확인하지 못했습니다. 고정 주소에서 다시 시도하세요.",
          422:"64자리 복구 코드와 숫자 4자리 PIN을 확인하세요.",
          503:"서버에서 저장을 확인하지 못했습니다. 잠시 후 다시 시도하세요."
        };
        el("pin-result").textContent=messages[r.status] || "저장 응답 오류 (HTTP "+r.status+").";
        return;
      }
      const data=await r.json();
      if(data.configured!==true) throw Error();
      form.reset();
      el("pin-result").textContent="저장했습니다. 주문·예약에서 새 PIN으로 로그인하세요.";
      window.dispatchEvent(new Event("pin-rotated"));
      await status();
    } catch {el("pin-result").textContent="저장 응답을 받지 못했습니다. 연결 상태를 확인하세요.";}
    finally {submit.disabled=false;}
  };
})();

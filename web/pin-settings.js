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
    event.target.reset();
    try {
      const r=await fetch("/api/reservations",{method:"POST",headers:{"Content-Type":"application/json"},
        cache:"no-store",redirect:"error",body:JSON.stringify({action:"recover-pin",code,pin})});
      if (!r.ok) throw Error();
      el("pin-result").textContent="저장했습니다. 주문·예약에서 새 PIN으로 로그인하세요.";
      window.dispatchEvent(new Event("pin-rotated"));
      await status();
    } catch {el("pin-result").textContent="저장을 확인하지 못했습니다. 코드의 유효기간과 연결 상태를 확인하세요.";}
  };
})();

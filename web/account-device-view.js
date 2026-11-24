const accountDevice = (() => {
  const el = id => document.getElementById(id);
  const form = el("device-form"), mode = el("device-mode"), note = el("device-note");
  const pin = el("device-pin"), confirm = el("device-confirm"), code = el("device-code"), key = el("viewer-key");
  let session = "", version = 0, expiry, hideCode;
  function clear() {
    ++version;
    session = "";
    clearTimeout(expiry);
    clearTimeout(hideCode);
    key.required = true;
    pin.value = confirm.value = code.value = note.textContent = "";
  }
  function layout() {
    confirm.parentElement.hidden = mode.value!=="register";
    confirm.required = mode.value==="register";
    code.parentElement.hidden = mode.value!=="pair";
    code.required = mode.value==="pair";
    confirm.value = code.value = pin.value = note.textContent = "";
    ++version;
  }
  mode.onchange = layout;
  key.addEventListener("input", clear);
  window.addEventListener("account-locked", clear);
  form.onsubmit = async event => {
    event.preventDefault();
    const action = mode.value;
    if (action==="register" && !key.value) { note.textContent="PC의 계좌 열람 키를 위 입력칸에 먼저 입력하세요."; return; }
    if (action==="register" && pin.value!==confirm.value) { note.textContent="두 PIN이 일치하지 않습니다."; return; }
    const revision = ++version;
    const body = JSON.stringify({action,pin:pin.value,code:code.value.replace(/[ -]/g,"")});
    const headers = {"Content-Type":"application/json"};
    if (action==="register") headers.Authorization = "Bearer "+key.value;
    const button = form.querySelector("button");
    button.disabled = true;
    note.textContent="확인 중…";
    try {
      const response = await fetch("/api/device-pin",{method:"POST",headers,body,cache:"no-store",redirect:"error",signal:AbortSignal.timeout(12000)});
      const data = await response.json();
      if (revision!==version) return;
      if (!response.ok) {
        note.textContent = response.status===429 ? "시도 한도에 도달했습니다. PC는 열람 키로 다시 등록하고, 휴대폰은 PC에서 새 연결 코드를 발급하세요." :
          response.status===401 ? "등록 상태와 입력값을 확인하세요." : "처리하지 못했습니다. 잠시 뒤 다시 시도하세요.";
        return;
      }
      if (action==="issue") {
        note.textContent = "휴대폰 연결 코드 "+data.code.match(/.{4}/g).join(" ")+" · 3분간 유효";
        clearTimeout(hideCode);
        hideCode=setTimeout(()=>{if(revision===version) note.textContent="연결 코드가 만료되었습니다.";},180000);
        return;
      }
      session=data.ticket;
      key.value="";
      key.required=false;
      mode.value="unlock";
      layout();
      note.textContent="PIN 인증 완료 · 15분간 조회 가능";
      clearTimeout(expiry);
      expiry=setTimeout(()=>el("account-lock").click(),15*60*1000);
      el("account-access").requestSubmit();
    } catch { if(revision===version) note.textContent="연결을 확인하고 다시 시도하세요."; }
    finally {button.disabled=false; pin.value=confirm.value=code.value="";}
  };
  layout();
  return {credential:()=>key.value || session};
})();

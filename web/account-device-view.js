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
  const dialog = el("pin-dialog"), globalForm = el("global-pin-form");
  const globalPin = el("global-pin"), globalNote = el("global-pin-note");
  const openLogin = el("open-pin-login");
  openLogin.onclick = () => {
    globalPin.value = globalNote.textContent = "";
    dialog.showModal();
    globalPin.focus();
  };
  el("close-pin-login").onclick = () => dialog.close();
  dialog.addEventListener("close", () => {globalPin.value = "";});
  el("pin-setup-link").onclick = () => {
    dialog.close();
    requestAnimationFrame(() => mode.focus());
  };
  async function authenticate(event) {
    event.preventDefault();
    const activeForm = event.currentTarget;
    const global = activeForm===globalForm;
    const action = global ? "unlock" : mode.value;
    const input = global ? globalPin : pin;
    const note = global ? globalNote : el("device-note");
    if (action==="register" && !key.value) { note.textContent="PC의 계좌 열람 키를 위 입력칸에 먼저 입력하세요."; return; }
    if (action==="register" && pin.value!==confirm.value) { note.textContent="두 PIN이 일치하지 않습니다."; return; }
    const revision = ++version;
    const body = JSON.stringify({action,pin:input.value,code:code.value.replace(/[ -]/g,"")});
    const headers = {"Content-Type":"application/json"};
    if (action==="register") headers.Authorization = "Bearer "+key.value;
    const button = activeForm.querySelector("button");
    button.disabled = true;
    note.textContent="확인 중…";
    try {
      const response = await fetch("/api/device-pin",{method:"POST",headers,body,cache:"no-store",redirect:"error",signal:AbortSignal.timeout(12000)});
      const data = await response.json();
      if (revision!==version) return;
      if (!response.ok) {
        if (response.status===401 && data.reason==="device_cookie_missing") {
          if (global) {
            note.textContent="이 브라우저는 먼저 기기 등록·연결이 필요합니다.";
            el("pin-setup-link").focus();
            return;
          }
          mode.value="register";
          layout();
          note.textContent="이 브라우저에 기기 등록 정보가 없습니다. PC에서는 위에 계좌 화면 열람 키를 입력한 뒤 아래에 사용할 PIN을 두 번 입력하고 확인을 누르세요. 휴대폰에서는 ‘휴대폰 연결’을 선택하세요.";
          key.focus();
          return;
        }
        note.textContent = response.status===429 ? "시도 한도에 도달했습니다. PC는 열람 키로 다시 등록하고, 휴대폰은 PC에서 새 연결 코드를 발급하세요." :
          response.status===401 ? ({
            register:"계좌 화면 열람 키를 확인하고 PIN을 다시 입력하세요.",
            pair:"연결 코드와 PIN을 확인하세요. 코드가 만료됐다면 새 코드를 발급하세요.",
            unlock:"이 브라우저에 등록한 PIN을 확인하세요. PIN을 잊었다면 PC에서는 ‘PC에 PIN 등록’으로 다시 등록하세요.",
            issue:"연결 코드를 발급하려면 이 PC에 등록한 PIN을 입력하세요."
          })[action] : "처리하지 못했습니다. 잠시 뒤 다시 시도하세요.";
        return;
      }
      if (action==="issue") {
        note.textContent = "휴대폰 연결 코드 "+data.code.match(/.{4}/g).join(" ")+" · 3분간 유효";
        clearTimeout(hideCode);
        hideCode=setTimeout(()=>{if(revision===version) note.textContent="연결 코드가 만료되었습니다.";},180000);
        return;
      }
      window.dispatchEvent(new CustomEvent("device-unlocked",{detail:data.ticket}));
      key.value="";
      key.required=false;
      mode.value="unlock";
      layout();
      note.textContent="PIN 인증 완료 · 15분간 조회 가능";
      if (global && dialog.open) dialog.close();

    } catch { if(revision===version) note.textContent="연결을 확인하고 다시 시도하세요."; }
    finally {button.disabled=false; input.value=""; if (!global) confirm.value=code.value="";}
  }
  form.onsubmit = globalForm.onsubmit = authenticate;
  window.addEventListener("device-unlocked",()=>{openLogin.textContent="PIN 재인증";});
  window.addEventListener("account-locked",()=>{openLogin.textContent="PIN 로그인";});
  window.addEventListener("device-unlocked",event=>{
    session=event.detail; key.value=""; key.required=false; clearTimeout(expiry);
    expiry=setTimeout(()=>el("account-lock").click(),15*60*1000);
    el("account-access").requestSubmit();
  });
  const board=document.querySelector("#watchlist iframe");
  const notifyBoard=()=>board?.contentWindow?.postMessage("cp-board-refresh",location.origin);
  window.addEventListener("device-unlocked",notifyBoard);
  window.addEventListener("unified-locked",notifyBoard);
  window.addEventListener("message",event=>{
    if(event.origin!==location.origin || event.source!==board?.contentWindow) return;
    if(event.data==="cp-board-unlocked") {
      key.required=false;
      el("account-access").requestSubmit();
      el("reservation-refresh").click();
    }
    if(event.data==="cp-board-locked") window.dispatchEvent(new Event("unified-locked"));
  });
  layout();
  return {credential:()=>key.value || session};
})();

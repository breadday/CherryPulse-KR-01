const CherryReservations = {
  attach({edit,sessionChanged}) {
    const el = id => document.getElementById(id);
    let signed = false, pending = false, generation = 0;
    const messages = {401:"보드 PIN 로그인이 필요합니다.",403:"요청 출처를 확인하세요.",404:"예약을 찾을 수 없습니다.",
      409:"같은 예약이 있거나 상태가 변경됐습니다. 목록에서 최신 예약을 선택하세요.",
      422:"종목·수량·가격과 미래 KRX 영업일을 확인하세요.",429:"로그인 시도가 많습니다. 잠시 후 다시 시도하세요."};
    async function api(method,body) {
      const response = await fetch("/api/reservations",{method,credentials:"same-origin",cache:"no-store",
        headers:body?{"Content-Type":"application/json"}:{},body:body?JSON.stringify(body):undefined,
        redirect:"error",signal:AbortSignal.timeout(18000)});
      if (!response.ok) throw Object.assign(new Error(),{status:response.status});
      return response.json();
    }
    function session(active) {
      signed = active;
      el("reservation-login").hidden = active;
      el("reservation-tools").hidden = !active;
      if (!active) el("reservation-list").replaceChildren();
      sessionChanged(active);
    }
    function error(e) {
      if (e.status===401) session(false);
      el("reservation-status").textContent = messages[e.status] || "서버 응답을 확인하지 못했습니다. 다시 조회하세요.";
    }
    function render(rows) {
      const list = el("reservation-list");
      list.replaceChildren();
      for (const row of rows) {
        const d = row.details;
        const item = document.createElement("div");
        item.className = "draft-row reservation-card";
        item.dataset.status = row.status;
        const header = document.createElement("div");
        header.className = "reservation-header";
        const name = document.createElement("strong");
        name.textContent = d.name;
        const code = document.createElement("small");
        code.textContent = d.code;
        const badge = document.createElement("span");
        badge.className = "reservation-state";
        badge.textContent = {scheduled:"예약 대기",due:"실행 시각 도달",dry_run:"실행 모의 검증 완료",error:"오류",expired:"만료",cancelled:"취소"}[row.status] || "상태 미확인";
        header.append(name,code,badge);
        const schedule = document.createElement("p");
        schedule.className = "reservation-time";
        schedule.textContent = "실행 예정 "+d.date+" "+d.time+" KST";
        const terms = document.createElement("p");
        terms.textContent = [d.side+" "+d.qty.toLocaleString("ko-KR")+"주",d.type+(d.price===null?"":" "+d.price.toLocaleString("ko-KR")+"원")].join(" · ");
        item.append(header,schedule,terms);
        if (row.processedAt) {
          const processed = document.createElement("p");
          const time = new Date(row.processedAt).toLocaleString("ko-KR",{timeZone:"Asia/Seoul"});
          processed.textContent = "처리 시각 "+time+" KST · DRY_RUN · 주문 전송 없음";
          if (row.errorCode) processed.textContent += " · "+row.errorCode;
          item.append(processed);
        }
        if (row.status==="scheduled") {
          const change = document.createElement("button"), cancel = document.createElement("button");
          change.className = cancel.className = "btn secondary";
          change.textContent = "서버 예약 수정";
          change.onclick = () => edit(row);
          cancel.textContent = "서버 예약 취소";
          cancel.onclick = () => {
            if (confirm([name.textContent,code.textContent,schedule.textContent,terms.textContent].join(" · ")+"\n예약을 취소할까요?")) mutate("DELETE",{id:row.id,version:row.version});
          };
          item.append(change," ",cancel);
        }
        list.append(item);
      }
      el("reservation-status").textContent = "서버 예약 "+rows.length+"건 · 모의 검증 전용";
    }
    async function refresh() {
      const current = ++generation;
      try {
        const {rows} = await api("GET");
        if (current!==generation) return;
        session(true);
        render(rows);
      } catch(e) {
        if (current!==generation) return;
        el("reservation-list").replaceChildren();
        error(e);
      }
    }
    async function mutate(method,body) {
      if (pending) return false;
      pending = true;
      try {
        await api(method,body);
        await refresh();
        return true;
      } catch(e) {
        if (e.status===409) await refresh();
        error(e);
        return false;
      } finally {pending=false;}
    }
    el("reservation-login").onsubmit = async event => {
      event.preventDefault();
      const field = el("reservation-pin"), pin = field.value;
      field.value = "";
      await mutate("POST",{action:"login",pin});
    };
    el("reservation-logout").onclick = async () => {
      if (pending) return;
      pending=true;
      try {await api("POST",{action:"logout"}); ++generation; session(false); el("reservation-status").textContent="로그아웃했습니다.";}
      catch(e){error(e);} finally {pending=false;}
    };
    window.addEventListener("pin-rotated",()=>{++generation;session(false);el("reservation-status").textContent="새 PIN으로 로그인하세요.";});
    el("reservation-refresh").onclick = refresh;
    window.setInterval(() => {
      if (signed && !pending && !document.hidden && location.hash==="#orders") refresh();
    },15000);
    window.addEventListener("pageshow",refresh);
    document.addEventListener("visibilitychange",()=>{if (!document.hidden && signed) refresh();});
    return {signedIn:()=>signed, save:(id,version,details)=>mutate(version?"PATCH":"POST",{id,version,details})};
  }
};

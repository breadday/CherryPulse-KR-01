"use strict";
(function expose(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (typeof document !== "undefined") {
    const button = document.getElementById("check-cloud-setup");
    const result = document.getElementById("cloud-setup-result");
    if (button && result) button.addEventListener("click", async () => {
      button.disabled = true;
      result.textContent = "설정 확인 중…";
      try { result.textContent = await api.checkSetup(fetch); }
      finally { button.disabled = false; }
    });
  }
})(globalThis, () => {
  async function checkSetup(fetcher) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    try {
      const response = await fetcher("/api/cloud-config", {cache: "no-store", credentials: "omit", signal: controller.signal});
      if (response.status === 404) return "연결 확인 API가 배포되지 않았습니다. 현재 초안은 이 브라우저에 저장됩니다.";
      const body = await response.json();
      if (body.configurationReady === true && response.ok && body.reason === "CONFIGURATION_ONLY") {
        return "프로젝트 URL·공개 키 설정 확인. 로그인·서버 저장 기능과 실제 연결 검증은 아직 준비 중입니다.";
      }
      if (body.reason === "PUBLISHABLE_KEY_MISSING") return "Cloudflare에 Supabase 공개 키 설정이 필요합니다. 비밀 키는 입력하지 마세요.";
      return "클라우드 설정을 확인하지 못했습니다. 프로젝트 주소와 공개 키 종류를 점검하세요.";
    } catch {
      return "연결 확인 응답을 받지 못했습니다. 기존 브라우저 초안은 유지됩니다.";
    } finally { clearTimeout(timeout); }
  }
  return {checkSetup};
});

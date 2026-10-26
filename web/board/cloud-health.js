"use strict";
// This script still runs if an earlier script failed to download or initialize.
if (document.getElementById("cloud-login-form")?.getAttribute("data-cloud-ready") !== "true") {
  const status = document.getElementById("cloud-status");
  if (status) status.textContent = "로그인 기능을 불러오지 못했습니다. Ctrl+F5로 새로고침하고, 계속되면 스크립트 차단 설정을 확인하세요.";
  for (const id of ["cloud-login"]) {
    const button = document.getElementById(id);
    if (button) button.disabled = true;
  }
}

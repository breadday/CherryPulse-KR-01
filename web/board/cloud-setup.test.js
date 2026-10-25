"use strict";
const assert = require("node:assert/strict");
const test = require("node:test");
const {checkSetup} = require("./cloud-setup.js");
test("setup UI reports missing worker and missing key without claiming connection", async () => {
  assert.match(await checkSetup(async () => new Response("missing", {status: 404})), /API가 배포되지/);
  assert.match(await checkSetup(async () => Response.json({reason: "PUBLISHABLE_KEY_MISSING"}, {status: 503})), /공개 키 설정이 필요/);
});
test("configured UI explicitly keeps login and database work pending", async () => {
  const result = await checkSetup(async (url, options) => {
    assert.equal(url, "/api/cloud-config"); assert.equal(options.credentials, "omit");
    return Response.json({configurationReady: true, reason: "CONFIGURATION_ONLY", publishableKey: "do-not-display"});
  });
  assert.match(result, /아직 준비 중/);
  assert.equal(result.includes("do-not-display"), false);
});
test("HTML fallback and unavailable network are recoverable", async () => {
  assert.match(await checkSetup(async () => new Response("<html>board</html>")), /기존 브라우저 초안은 유지/);
  assert.match(await checkSetup(async () => { throw new Error("private transport detail"); }), /기존 브라우저 초안은 유지/);
});

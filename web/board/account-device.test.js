const {test} = require("node:test");
const assert = require("node:assert/strict");
const {cookieName,ticket,validTicket} = require("../lib/account-device");
test("read ticket requires its issuing browser, expiry and signing key", () => {
  process.env.CHERRYPLUS_DEVICE_RPC_KEY = "test-rpc-only";
  process.env.CHERRYPLUS_ACCOUNT_VIEW_KEY = "test-viewer-only";
  const device = "a".repeat(64);
  const req = {headers:{cookie:cookieName+"="+device}};
  const token = ticket(device);
  assert.equal(validTicket(req,token),true);
  assert.equal(validTicket({headers:{}},token),false);
  assert.equal(validTicket(req,ticket("b".repeat(64))),false);
  assert.equal(validTicket(req,ticket(device,Date.now()-900001)),false);
  process.env.CHERRYPLUS_ACCOUNT_VIEW_KEY = "rotated";
  assert.equal(validTicket(req,token),false);
});

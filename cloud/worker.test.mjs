import assert from "node:assert/strict";
import test from "node:test";
import {readFileSync} from "node:fs";
import worker from "./worker.mjs";
const url = "https://qrrrnxmsbrkqueaabjdr.supabase.co";
const request = (path, method = "GET") => new Request(`https://board.test${path}`, {method});

test("missing key fails closed and does not claim login or CRUD readiness", async () => {
  const response = await worker.fetch(request("/api/cloud-config"), {SUPABASE_URL: url});
  const body = await response.json();
  assert.equal(response.status, 503);
  assert.equal(body.configurationReady, false);
  assert.deepEqual(body.capabilities, {authentication: false, boardCrud: false, engine: false});
});

test("only the designated project and a publishable key can be exposed", async () => {
  const key = "sb_publishable_synthetic_test_value_1234";
  const response = await worker.fetch(request("/api/cloud-config"), {
    SUPABASE_URL: url, SUPABASE_PUBLISHABLE_KEY: key, SUPABASE_SECRET_KEY: "synthetic-private-value",
  });
  const body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("Cache-Control"), "no-store");
  assert.equal(body.publishableKey, key);
  assert.equal(JSON.stringify(body).includes("synthetic-private-value"), false);
  const wrong = await worker.fetch(request("/api/cloud-config"), {SUPABASE_URL: "https://other.supabase.co", SUPABASE_PUBLISHABLE_KEY: key});
  assert.equal(wrong.status, 503);
  assert.equal((await wrong.text()).includes(key), false);
});

test("secret and legacy keys in the public binding are never returned", async () => {
  for (const key of ["sb_secret_synthetic1234567890", "eyJhbGciOiJIUzI1NiJ9.synthetic.signature", "service_role", 42]) {
    const response = await worker.fetch(request("/api/cloud-config"), {SUPABASE_URL: url, SUPABASE_PUBLISHABLE_KEY: key});
    assert.equal(response.status, 503);
    assert.equal((await response.text()).includes(String(key)), false);
  }
});

test("API routes do not fall through to a static success page", async () => {
  const env = {ASSETS: {fetch() { throw new Error("Must not serve assets for API requests"); }}};
  assert.equal((await worker.fetch(request("/api/items"), env)).status, 404);
  assert.equal((await worker.fetch(request("/api/cloud-config", "POST"), env)).status, 405);
});

test("board assets retain their own request path and only web is published", async () => {
  const incoming = request("/board/");
  const result = await worker.fetch(incoming, {ASSETS: {fetch(req) {
    assert.equal(req, incoming); return new Response("board");
  }}});
  assert.equal(await result.text(), "board");
  const config = JSON.parse(readFileSync(new URL("../wrangler.jsonc", import.meta.url), "utf8"));
  assert.equal(config.assets.directory, "./web");
  assert.deepEqual(config.assets.run_worker_first, ["/api/*"]);
});

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

const env = {SUPABASE_URL: url, SUPABASE_PUBLISHABLE_KEY: 'sb_publishable_synthetic_public_test_key'};
const auth = {Authorization: 'Bearer synthetic_jwt_token_value_12345'};
const snapshot = {format: 'cherrypulse-board-draft', schemaVersion: 1, symbols: [], patterns: []};
const saveBody = {snapshot, expectedRevision: 0, requestKey: '48c0800c-f6ee-4b7a-84a9-e86dc11a3def'};
const {handleRequest} = await import('./worker.mjs');
const put = (body, headers = {}) => new Request('https://board.test/api/board', {method: 'PUT', headers: {...auth, 'Content-Type': 'application/json', ...headers}, body: JSON.stringify(body)});
test('board requires a bearer token and rejects cross-origin mutations', async () => {
  assert.equal((await handleRequest(request('/api/board'), env)).status, 401);
  assert.equal((await handleRequest(put(saveBody, {Origin: 'https://other.test'}), env)).status, 403);
});
test('save validates links, revision, request keys and body size before calling the DB', async () => {
  let calls = 0;
  const fetcher = () => { calls++; throw new Error(); };
  for (const body of [{...saveBody, expectedRevision: -1}, {...saveBody, requestKey: 'bad'}, {...saveBody, snapshot: {...snapshot, symbols: [{code: '005930', name: '삼성', patternId: 'missing'}]}}]) {
    assert.equal((await handleRequest(put(body), env, fetcher)).status, 422);
  }
  assert.equal((await handleRequest(put({...saveBody, extra: 'x'.repeat(1048576)}), env, fetcher)).status, 413);
  assert.equal(calls, 0);
});
test('RPC uses the user bearer token; DB conflicts and failures expose no upstream details', async () => {
  const conflict = await handleRequest(put(saveBody), env, async (target, options) => {
    assert.equal(target, `${url}/rest/v1/rpc/cp_save_board`);
    assert.equal(options.headers.Authorization, auth.Authorization);
    assert.equal(options.headers.apikey, env.SUPABASE_PUBLISHABLE_KEY);
    assert.deepEqual(JSON.parse(options.body), {p_snapshot: snapshot, p_expected_revision: 0, p_request_key: saveBody.requestKey});
    return Response.json({status: 412, code: 'VERSION_CONFLICT'});
  });
  assert.equal(conflict.status, 412);
  const failed = await handleRequest(put(saveBody), env, async () => new Response('private DB information', {status: 500}));
  assert.equal(failed.status, 502); assert.equal((await failed.text()).includes('private DB'), false);
});
test('load returns versioned snapshot without caching and network failure never looks empty', async () => {
  const req = new Request('https://board.test/api/board', {headers: auth});
  const loaded = await handleRequest(req, env, async (target, options) => {
    assert.equal(target, `${url}/rest/v1/rpc/cp_load_board`); assert.equal(options.body, '{}');
    return Response.json({revision: 1, snapshot});
  });
  assert.equal(loaded.headers.get('cache-control'), 'no-store');
  assert.deepEqual((await loaded.json()).snapshot, snapshot);
  const failed = await handleRequest(req, env, async () => { throw new Error('timeout'); });
  assert.equal(failed.status, 502);
});

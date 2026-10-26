import backup from "../web/board/board-backup.js";
const capabilities = Object.freeze({authentication: true, boardCrud: true, engine: false});
const unavailable = Object.freeze({authentication: false, boardCrud: false, engine: false});
const projectUrl = "https://qrrrnxmsbrkqueaabjdr.supabase.co";
const MAX_BYTES = 1048576;
function json(body, status = 200, extraHeaders = {}) {
  return Response.json(body, {status, headers: {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", ...extraHeaders}});
}
export function publicConfiguration(env) {
  if (env.SUPABASE_URL !== projectUrl) return {configurationReady: false, reason: "PROJECT_URL_MISMATCH", capabilities: unavailable};
  const key = env.SUPABASE_PUBLISHABLE_KEY;
  if (!key) return {configurationReady: false, reason: "PUBLISHABLE_KEY_MISSING", capabilities: unavailable};
  if (typeof key !== "string" || !/^sb_publishable_[A-Za-z0-9_-]{16,256}$/.test(key)) {
    return {configurationReady: false, reason: "PUBLISHABLE_KEY_FORMAT_UNSUPPORTED", capabilities: unavailable};
  }
  return {configurationReady: true, reason: "CONFIGURATION_ONLY", supabaseUrl: projectUrl, publishableKey: key, capabilities};
}
function error(code, status) { return json({error: {code}}, status); }
async function boundedJson(request) {
  if (!request.headers.get("content-type")?.startsWith("application/json")) throw new Error("CONTENT_TYPE");
  const reader = request.body?.getReader();
  if (!reader) throw new Error("JSON");
  const parts = []; let length = 0;
  while (true) {
    const {done, value} = await reader.read();
    if (done) break;
    length += value.byteLength;
    if (length > MAX_BYTES) { await reader.cancel(); throw new Error("SIZE"); }
    parts.push(value);
  }
  return JSON.parse(await new Blob(parts).text());
}
export async function handleRequest(request, env, fetcher = fetch) {
  const {pathname, origin} = new URL(request.url);
  if (!pathname.startsWith("/api/")) return env.ASSETS.fetch(request);
  if (!["/api/cloud-config", "/api/board"].includes(pathname)) return error("NOT_IMPLEMENTED", 404);
  if (pathname === "/api/cloud-config") {
    if (request.method !== "GET") return json({error: {code: "METHOD_NOT_ALLOWED"}}, 405, {Allow: "GET"});
    const config = publicConfiguration(env);
    return json(config, config.configurationReady ? 200 : 503);
  }
  if (!["GET", "PUT"].includes(request.method)) return json({error: {code: "METHOD_NOT_ALLOWED"}}, 405, {Allow: "GET, PUT"});
  if (request.headers.get("origin") && request.headers.get("origin") !== origin) return error("ORIGIN_REJECTED", 403);
  const config = publicConfiguration(env);
  if (!config.configurationReady) return error("NOT_CONFIGURED", 503);
  const authorization = request.headers.get("authorization");
  if (!authorization || !/^Bearer [A-Za-z0-9._-]{20,8192}$/.test(authorization)) return error("UNAUTHENTICATED", 401);
  let args = {}, name = "cp_load_board";
  if (request.method === "PUT") {
    let body;
    try { body = await boundedJson(request); }
    catch (e) { return error(e.message === "SIZE" ? "PAYLOAD_TOO_LARGE" : "VALIDATION_FAILED", e.message === "SIZE" ? 413 : 422); }
    try {
      if (!body || Object.keys(body).some(key => !["snapshot", "expectedRevision", "requestKey"].includes(key)) ||
          !Number.isInteger(body.expectedRevision) || body.expectedRevision < 0 || body.expectedRevision >= 2147483647 ||
          !/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i.test(body.requestKey)) throw new Error();
      backup.parseBoardBackup(JSON.stringify(body.snapshot));
    } catch { return error("VALIDATION_FAILED", 422); }
    name = "cp_save_board";
    args = {p_snapshot: body.snapshot, p_expected_revision: body.expectedRevision, p_request_key: body.requestKey};
  }
  try {
    const response = await fetcher(`${projectUrl}/rest/v1/rpc/${name}`, {
      method: "POST", headers: {apikey: config.publishableKey, Authorization: authorization, "Content-Type": "application/json"},
      body: JSON.stringify(args), signal: AbortSignal.timeout(10000), redirect: "error",
    });
    if (!response.ok) return error(response.status === 401 || response.status === 403 ? "UNAUTHENTICATED" : "DATABASE_UNAVAILABLE", response.status === 401 || response.status === 403 ? 401 : 502);
    const body = await response.json();
    if (body?.status) {
      const codes = {401: "UNAUTHENTICATED", 409: "IDEMPOTENCY_MISMATCH", 412: "VERSION_CONFLICT", 422: "VALIDATION_FAILED", 429: "RATE_LIMITED"};
      return error(codes[body.status] || "DATABASE_UNAVAILABLE", codes[body.status] ? body.status : 502);
    }
    if (!Number.isInteger(body?.revision) || body.revision < 0) return error("DATABASE_UNAVAILABLE", 502);
    return json(body);
  } catch { return error("DATABASE_UNAVAILABLE", 502); }
}
export default {fetch(request, env) { return handleRequest(request, env); }};

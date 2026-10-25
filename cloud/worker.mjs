// This stage exposes configuration readiness, not authentication or database CRUD.
const capabilities = Object.freeze({authentication: false, boardCrud: false, engine: false});
const projectUrl = "https://qrrrnxmsbrkqueaabjdr.supabase.co";

function json(body, status = 200, extraHeaders = {}) {
  return Response.json(body, {status, headers: {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    ...extraHeaders,
  }});
}

export function publicConfiguration(env) {
  // Pin to the user-designated project; do not send users to an arbitrary origin.
  if (env.SUPABASE_URL !== projectUrl) {
    return {configurationReady: false, reason: "PROJECT_URL_MISMATCH", capabilities};
  }
  const key = env.SUPABASE_PUBLISHABLE_KEY;
  if (!key) return {configurationReady: false, reason: "PUBLISHABLE_KEY_MISSING", capabilities};
  // Only modern publishable keys are intentionally public here. Never echo secret,
  // service_role, legacy JWTs, or arbitrary environment values to the browser.
  if (typeof key !== "string" || !/^sb_publishable_[A-Za-z0-9_-]{16,256}$/.test(key)) {
    return {configurationReady: false, reason: "PUBLISHABLE_KEY_FORMAT_UNSUPPORTED", capabilities};
  }
  return {configurationReady: true, reason: "CONFIGURATION_ONLY", supabaseUrl: projectUrl,
    publishableKey: key, capabilities};
}

export default {
  async fetch(request, env) {
    const {pathname} = new URL(request.url);
    if (pathname.startsWith("/api/")) {
      if (pathname !== "/api/cloud-config") return json({error: {code: "NOT_IMPLEMENTED"}}, 404);
      if (request.method !== "GET") return json({error: {code: "METHOD_NOT_ALLOWED"}}, 405, {Allow: "GET"});
      const configuration = publicConfiguration(env);
      return json(configuration, configuration.configurationReady ? 200 : 503);
    }
    return env.ASSETS.fetch(request);
  },
};

"use strict";
(function expose(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.CherryPulseCloud = api;
})(globalThis, () => {
  class CloudError extends Error { constructor(code) { super(code); this.code = code; } }
  function createClient(fetcher, uuid, backup) {
    let config, session = null, revision = null, pending = null;
    async function request(url, options = {}) {
      let response, body;
      try {
        response = await fetcher(url, {...options, cache: "no-store", credentials: "omit", signal: AbortSignal.timeout(12000), redirect: "error"});
        body = response.status === 204 ? {} : await response.json();
      } catch { throw new CloudError("NETWORK_ERROR"); }
      if (!response.ok) {
        if (response.status === 401) { session = null; revision = null; pending = null; }
        throw new CloudError(body?.error?.code || (response.status === 400 ? "LOGIN_FAILED" : `HTTP_${response.status}`));
      }
      return body;
    }
    async function configure() {
      const value = await request("/api/cloud-config");
      if (value.supabaseUrl !== "https://qrrrnxmsbrkqueaabjdr.supabase.co" ||
          !/^sb_publishable_[A-Za-z0-9_-]{16,256}$/.test(value.publishableKey) || !value.capabilities?.boardCrud) throw new CloudError("NOT_CONFIGURED");
      config = value;
    }
    async function auth(email, password, signup = false) {
      session = null; revision = null; pending = null;
      if (!config) await configure();
      const body = await request(`${config.supabaseUrl}/auth/v1/${signup ? "signup" : "token?grant_type=password"}`, {
        method: "POST", headers: {apikey: config.publishableKey, "Content-Type": "application/json"}, body: JSON.stringify({email, password}),
      });
      if (body.access_token && body.user?.id) session = {token: body.access_token, id: body.user.id};
      return {signedIn: !!session};
    }
    function headers() {
      if (!session) throw new CloudError("UNAUTHENTICATED");
      return {Authorization: `Bearer ${session.token}`, "Content-Type": "application/json"};
    }
    async function read() {
      const body = await request("/api/board", {headers: headers()});
      if (!Number.isInteger(body.revision) || body.revision < 0 || (body.revision > 0 && !body.snapshot) ||
          (body.revision === 0 && body.snapshot !== null)) throw new CloudError("INVALID_RESPONSE");
      if (body.snapshot) backup.parseBoardBackup(JSON.stringify(body.snapshot));
      return body;
    }
    async function inspect() {
      const body = await read();
      // Existing remote data must be explicitly loaded before overwriting it.
      if (body.revision === 0) revision = 0;
      return body;
    }
    async function load() {
      if (pending) throw new CloudError("SAVE_UNCONFIRMED");
      return read();
    }
    function acceptLoaded(value) { revision = value.revision; }
    async function save(state, retry = false) {
      if (retry && !pending) throw new CloudError("NO_PENDING_SAVE");
      const snapshot = retry && pending ? pending.snapshot : JSON.parse(backup.serializeBoardBackup(state));
      if (revision === null) throw new CloudError("LOAD_REQUIRED");
      if (pending && JSON.stringify(pending.snapshot) !== JSON.stringify(snapshot)) throw new CloudError("SAVE_UNCONFIRMED");
      if (!pending) pending = {snapshot, expectedRevision: revision, requestKey: uuid()};
      let body;
      try { body = await request("/api/board", {method: "PUT", headers: headers(), body: JSON.stringify(pending)}); }
      catch (e) {
        if (["VERSION_CONFLICT", "VALIDATION_FAILED", "IDEMPOTENCY_MISMATCH"].includes(e.code)) { pending = null; revision = null; }
        throw e;
      }
      if (!Number.isInteger(body.revision) || body.revision !== pending.expectedRevision + 1) throw new CloudError("INVALID_RESPONSE");
      revision = body.revision; pending = null;
      return body;
    }
    async function logout() {
      const old = session;
      session = null; revision = null; pending = null;
      if (old && config) await request(`${config.supabaseUrl}/auth/v1/logout?scope=local`, {
        method: "POST", headers: {apikey: config.publishableKey, Authorization: `Bearer ${old.token}`},
      });
    }
    return {auth, inspect, load, acceptLoaded, save, retry: () => save(null, true), logout, signedIn: () => !!session};
  }
  return {CloudError, createClient};
});

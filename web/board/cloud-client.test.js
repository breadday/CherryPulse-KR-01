const test = require('node:test');
const assert = require('node:assert/strict');
const {createClient} = require('./cloud-client.js');
const backup = require('./board-backup.js');
const key = 'sb_publishable_synthetic_public_test_key';
const draft = {symbols: [], patterns: []};
function setup(handler) {
  let sequence = 0;
  const client = createClient(async (url, options) => {
    assert.equal(options.credentials, 'omit');
    if (url === '/api/cloud-config') return Response.json({supabaseUrl: 'https://qrrrnxmsbrkqueaabjdr.supabase.co', publishableKey: key, capabilities: {boardCrud: true}});
    if (url.includes('/auth/v1/token')) return Response.json({access_token: 'synthetic-token', user: {id: 'owner'}});
    return handler(url, options);
  }, () => `key-${++sequence}`, backup);
  return client;
}
test('existing server data cannot be overwritten before explicit load acceptance', async () => {
  const client = setup(async () => Response.json({revision: 4, snapshot: JSON.parse(backup.serializeBoardBackup(draft))}));
  await client.auth('test@example.invalid', 'synthetic-password');
  await client.inspect();
  await assert.rejects(client.save(draft), {code: 'LOAD_REQUIRED'});
  const loaded = await client.load();
  await assert.rejects(client.save(draft), {code: 'LOAD_REQUIRED'});
  client.acceptLoaded(loaded);
});
test('response loss reuses the identical idempotency key and payload even after local editing', async () => {
  const sent = []; let fail = true;
  const client = setup(async (url, options) => {
    if (options.method !== 'PUT') return Response.json({revision: 0, snapshot: null});
    sent.push(JSON.parse(options.body));
    if (fail) { fail = false; throw new Error('response lost'); }
    return Response.json({revision: 1});
  });
  await client.auth('test@example.invalid', 'synthetic-password'); await client.inspect();
  await assert.rejects(client.save(draft), {code: 'NETWORK_ERROR'});
  await assert.rejects(client.load(), {code: 'SAVE_UNCONFIRMED'});
  await assert.rejects(client.save({symbols: [{code: '005930', name: '삼성전자'}], patterns: []}), {code: 'SAVE_UNCONFIRMED'});
  await client.retry();
  assert.deepEqual(sent[0], sent[1]);
  await assert.rejects(client.retry(), {code: 'NO_PENDING_SAVE'});
});
test('conflict requires a new load and never retries with a guessed revision', async () => {
  let writes = 0;
  const client = setup(async (url, options) => {
    if (options.method !== 'PUT') return Response.json({revision: 0, snapshot: null});
    writes++; return Response.json({error: {code: 'VERSION_CONFLICT'}}, {status: 412});
  });
  await client.auth('a@b.invalid', 'synthetic-password'); await client.inspect();
  await assert.rejects(client.save(draft), {code: 'VERSION_CONFLICT'});
  await assert.rejects(client.save(draft), {code: 'LOAD_REQUIRED'});
  assert.equal(writes, 1);
});
test('logout clears the local session even if remote revocation fails', async () => {
  const client = setup(async () => { throw new Error('offline'); });
  await client.auth('a@b.invalid', 'synthetic-password');
  await assert.rejects(client.logout(), {code: 'NETWORK_ERROR'});
  assert.equal(client.signedIn(), false);
  await assert.rejects(client.load(), {code: 'UNAUTHENTICATED'});
});
test('invalid remote snapshots never reach local storage or revision acceptance', async () => {
  const client = setup(async () => Response.json({revision: 1, snapshot: {symbols: [], patterns: []}}));
  await client.auth('a@b.invalid', 'synthetic-password');
  await assert.rejects(client.load());
  await assert.rejects(client.save(draft), {code: 'LOAD_REQUIRED'});
});

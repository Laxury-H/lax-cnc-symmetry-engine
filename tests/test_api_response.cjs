const { readFileSync } = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const { test } = require('node:test');

const context = vm.createContext({ document: { addEventListener() {} } });
vm.runInContext(readFileSync('src/web/static/js/app.js', 'utf8'), context);

test('API handles JSON success, JSON errors and HTML gateway failures', async () => {
  const read = context.readApiResponse;
  assert.equal((await read(new Response('{"session_id":"test"}'))).session_id, 'test');
  await assert.rejects(read(new Response('{"error":"Invalid DXF"}', { status: 400 })), /Invalid DXF/);
  await assert.rejects(read(new Response('<html>Bad Gateway</html>', { status: 502 })), /HTTP 502/);
  await assert.rejects(read(new Response('<html>Error</html>', { status: 200 })), /HTTP 200/);
  await assert.rejects(read(new Response('null')), /không hợp lệ/);
});

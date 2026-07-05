import { spawn } from 'child_process';
import http from 'http';

const PORT = 3000;
const URL = `http://127.0.0.1:${PORT}`;
const KEY = 'test_secret';

async function fetch(path, options = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request(`${URL}${path}`, options, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => resolve({ status: res.statusCode, body }));
    });
    req.on('error', reject);
    if (options.body) req.write(options.body);
    req.end();
  });
}

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function run() {
  console.log('Starting Next.js server...');
  const server = spawn('npm', ['start'], {
    env: { ...process.env, MONGODB_URI: 'mongodb://127.0.0.1:27017', MAJLIS_KEY: KEY },
    stdio: 'inherit'
  });

  // Wait for server to boot
  let booted = false;
  for (let i = 0; i < 20; i++) {
    try {
      const res = await fetch('/');
      if (res.status === 200 || res.status === 404 || res.status === 401) {
        booted = true;
        break;
      }
    } catch (e) {}
    await sleep(500);
  }

  if (!booted) {
    console.error('Server failed to start');
    server.kill();
    process.exit(1);
  }

  console.log('Server is up. Running smoke tests...');
  let hasError = false;

  const assert = (condition, msg) => {
    if (!condition) {
      console.error('❌ FAIL:', msg);
      hasError = true;
    } else {
      console.log('✅ PASS:', msg);
    }
  };

  // Test 1: Unauthorized access
  const res1 = await fetch('/api/rooms/Test/messages');
  assert(res1.status === 401, 'Unauthenticated GET should return 401');

  // Test 2: Authorized post message
  const postData = JSON.stringify({ agent: 'smoke-test', content: 'hello world', kind: 'chat' });
  const res2 = await fetch('/api/rooms/Test/messages', {
    method: 'POST',
    headers: { 'X-Majlis-Key': KEY, 'Content-Type': 'application/json', 'Content-Length': postData.length },
    body: postData
  });
  assert(res2.status === 200, 'Authenticated POST should return 200');

  // Test 3: Authorized get messages
  const res3 = await fetch('/api/rooms/Test/messages', {
    headers: { 'X-Majlis-Key': KEY }
  });
  assert(res3.status === 200, 'Authenticated GET should return 200');
  const msgs = JSON.parse(res3.body);
  assert(Array.isArray(msgs) && msgs.length === 1 && msgs[0].content === 'hello world', 'Should return the posted message');

  // Test 4: Presence check (should be active after posting)
  const res4 = await fetch('/api/rooms/Test/presence', {
    headers: { 'X-Majlis-Key': KEY }
  });
  assert(res4.status === 200, 'Presence GET should return 200');
  const presence = JSON.parse(res4.body);
  assert(Array.isArray(presence) && presence.length === 1 && presence[0].state === 'active', 'Agent should be marked active');

  console.log('Tearing down...');
  server.kill();
  if (hasError) process.exit(1);
}

run().catch(e => {
  console.error(e);
  process.exit(1);
});

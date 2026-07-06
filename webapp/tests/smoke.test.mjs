import { spawn } from 'child_process';
import http from 'http';

const PORT = 3000;
const URL = `http://127.0.0.1:${PORT}`;
// The hosted webapp authenticates via GitHub (NextAuth session or a Bearer
// PAT resolved through GitHub's /user endpoint) — it has no shared-secret
// header at all, unlike the local FastAPI server's X-Majlis-Key. Full
// authenticated-path testing needs a real GitHub PAT whose login is on
// ALLOWED_GITHUB_LOGINS, provided via the TEST_GITHUB_TOKEN secret; without
// it we still verify the unauthenticated path, and skip the rest loudly
// rather than assert against a header this app doesn't check.
const TEST_TOKEN = process.env.TEST_GITHUB_TOKEN || '';

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
  const npmCommand = process.platform === 'win32' ? (process.env.ComSpec || 'cmd.exe') : 'npm';
  const npmArgs = process.platform === 'win32' ? ['/d', '/s', '/c', 'npm start'] : ['start'];
  const server = spawn(npmCommand, npmArgs, {
    env: {
      ...process.env,
      MONGODB_URI: process.env.MONGODB_URI || 'mongodb://127.0.0.1:27017/majlis-ci',
      NEXTAUTH_SECRET: process.env.NEXTAUTH_SECRET || 'ci-test-secret-not-for-production',
      NEXTAUTH_URL: process.env.NEXTAUTH_URL || URL,
    },
    stdio: 'inherit'
  });

  // Wait for server to boot
  let booted = false;
  for (let i = 0; i < 20; i++) {
    try {
      const res = await fetch('/');
      if (res.status === 200 || res.status === 404 || res.status === 401 || res.status === 307) {
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

  // Test 1: unauthenticated access — this works with zero configuration.
  const res1 = await fetch('/api/rooms/Test/messages');
  assert(res1.status === 401, 'Unauthenticated GET should return 401');

  if (!TEST_TOKEN) {
    console.log('SKIP: authenticated-path tests (no TEST_GITHUB_TOKEN secret configured — see comment at top of this file).');
  } else {
    const authHeaders = { Authorization: `Bearer ${TEST_TOKEN}` };

    // Test 2: authorized post message
    const postData = JSON.stringify({ agent: 'smoke-test', content: 'hello world', kind: 'chat' });
    const res2 = await fetch('/api/rooms/Test/messages', {
      method: 'POST',
      headers: { ...authHeaders, 'Content-Type': 'application/json', 'Content-Length': postData.length },
      body: postData
    });
    assert(res2.status === 200, 'Authenticated POST should return 200');

    // Test 3: authorized get messages
    const res3 = await fetch('/api/rooms/Test/messages', { headers: authHeaders });
    assert(res3.status === 200, 'Authenticated GET should return 200');
    const msgs = JSON.parse(res3.body);
    assert(Array.isArray(msgs) && msgs.some(m => m.content === 'hello world'), 'Should return the posted message');

    // Test 4: presence check (should be active after posting)
    const res4 = await fetch('/api/rooms/Test/presence', { headers: authHeaders });
    assert(res4.status === 200, 'Presence GET should return 200');
    const presence = JSON.parse(res4.body);
    assert(Array.isArray(presence) && presence.some(p => p.state === 'active'), 'Agent should be marked active');
  }

  console.log('Tearing down...');
  server.kill();
  if (hasError) process.exit(1);
}

run().catch(e => {
  console.error(e);
  process.exit(1);
});

/**
 * Quick cookie extract — uses browser-level CDP endpoint
 */
const WebSocket = require('ws');
const http = require('http');

const CDP_PORT = 9515;
const GROK2API = 'http://127.0.0.1:8000';
const ADMIN_KEY = 'grok2api';

async function main() {
  // 1. Get browser WebSocket URL
  const version = await httpGet(`http://127.0.0.1:${CDP_PORT}/json/version`);
  const browserWsUrl = version.webSocketDebuggerUrl;
  console.log(`🔌 Connecting to: ${browserWsUrl}`);

  // 2. Connect and get cookies
  const cookies = await cdpGetCookies(browserWsUrl);
  console.log(`🍪 Total cookies: ${cookies.length}`);

  // 3. Filter grok.com cookies
  const grokCookies = cookies.filter(c => 
    c.domain.includes('grok.com') || c.domain.includes('x.ai')
  );
  console.log(`🎯 grok.com/x.ai cookies: ${grokCookies.length}`);
  
  for (const c of grokCookies) {
    const val = c.value.length > 30 ? c.value.substring(0, 30) + '...' : c.value;
    console.log(`  ${c.name} (${c.domain}) = ${val}`);
  }

  // 4. Find SSO token
  const sso = grokCookies.find(c => c.name === 'sso' || c.name === 'sso_rw') ||
              grokCookies.find(c => c.name.startsWith('sso'));
  
  if (!sso) {
    console.log('\n⚠️ No SSO cookie found. Looking for auth tokens...');
    const authCookies = grokCookies.filter(c => 
      c.name.includes('auth') || c.name.includes('token') || c.name.includes('session')
    );
    for (const c of authCookies) {
      console.log(`  🔑 ${c.name} = ${c.value.substring(0, 40)}...`);
    }
    
    // Try using the longest cookie as token (likely the JWT/SSO)
    if (grokCookies.length > 0) {
      const longest = grokCookies.reduce((a, b) => a.value.length > b.value.length ? a : b);
      console.log(`\n💡 Longest cookie: ${longest.name} (${longest.value.length} chars)`);
      console.log(`   Trying this as token...`);
      await pushToken(longest.value);
    }
    return;
  }

  console.log(`\n✅ SSO token found: ${sso.name} = ${sso.value.substring(0, 20)}...`);
  
  // Save backup
  require('fs').writeFileSync(
    require('path').join(__dirname, 'last_sso_cookie.txt'), 
    sso.value
  );
  
  // 5. Push to grok2api
  await pushToken(sso.value);
}

function cdpGetCookies(wsUrl) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(wsUrl, { 
      handshakeTimeout: 5000,
      perMessageDeflate: false,
    });
    const id = 1;

    ws.on('open', () => {
      console.log('✅ WebSocket connected');
      ws.send(JSON.stringify({
        id,
        method: 'Storage.getCookies',
        params: {}
      }));
    });

    ws.on('message', (data) => {
      try {
        const msg = JSON.parse(data.toString());
        if (msg.id === id) {
          ws.close();
          resolve(msg.result?.cookies || []);
        }
      } catch {}
    });

    ws.on('error', (err) => {
      console.log(`⚠️ WS error: ${err.message}`);
      reject(err);
    });

    setTimeout(() => {
      ws.close();
      reject(new Error('CDP WebSocket timeout (20s)'));
    }, 20000);
  });
}

async function pushToken(token) {
  console.log('\n🚀 Pushing to grok2api...');
  
  // List existing tokens
  const list = await httpGetAuth(`${GROK2API}/admin/api/tokens`);
  const existing = list.tokens || [];
  console.log(`📊 Existing tokens: ${existing.length}`);
  
  if (existing.length > 0 && existing[0].token === token) {
    console.log('✅ Token unchanged.');
    return;
  }
  
  // Add new token
  const result = await httpPostAuth(`${GROK2API}/admin/api/tokens/add`, {
    tokens: [token],
    pool: 'auto',
    tags: ['cdp-refresh', new Date().toISOString().split('T')[0]]
  });
  
  console.log(`✅ Result: ${JSON.stringify(result)}`);
  
  // Quick test
  console.log('\n🧪 Testing Grok API...');
  const models = await httpGet(`${GROK2API}/v1/models`);
  console.log(`📋 Models: ${(models.data || []).map(m => m.id).join(', ')}`);
}

function httpGet(url) {
  return new Promise((resolve, reject) => {
    http.get(url, (res) => {
      let d = '';
      res.on('data', c => d += c);
      res.on('end', () => { try { resolve(JSON.parse(d)); } catch { resolve(d); } });
    }).on('error', reject);
  });
}

function httpGetAuth(url) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    http.get({ hostname: u.hostname, port: u.port, path: u.pathname, 
      headers: { 'Authorization': `Bearer ${ADMIN_KEY}` }
    }, (res) => {
      let d = '';
      res.on('data', c => d += c);
      res.on('end', () => { try { resolve(JSON.parse(d)); } catch { resolve(d); } });
    }).on('error', reject);
  });
}

function httpPostAuth(url, body) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const data = JSON.stringify(body);
    const req = http.request({
      hostname: u.hostname, port: u.port, path: u.pathname,
      method: 'POST',
      headers: { 
        'Authorization': `Bearer ${ADMIN_KEY}`,
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(data),
      }
    }, (res) => {
      let d = '';
      res.on('data', c => d += c);
      res.on('end', () => { try { resolve(JSON.parse(d)); } catch { resolve(d); } });
    });
    req.on('error', reject);
    req.write(data);
    req.end();
  });
}

main().catch(err => { console.error('💥', err.message); process.exit(1); });

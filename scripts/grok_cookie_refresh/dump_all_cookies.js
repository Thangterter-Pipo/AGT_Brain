const http = require('http');
const WebSocket = require('ws');

async function httpReq(method, urlStr) {
  return new Promise((resolve, reject) => {
    const url = new URL(urlStr);
    const options = {
      hostname: url.hostname,
      port: url.port,
      path: url.pathname + url.search,
      method,
      timeout: 5000,
    };
    const req = http.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try { resolve({ status: res.statusCode, data: JSON.parse(data) }); }
        catch { resolve({ status: res.statusCode, data }); }
      });
    });
    req.on('error', reject);
    req.end();
  });
}

async function getBrowserCdpUrl() {
  const resp = await httpReq('GET', `http://127.0.0.1:9515/json/version`);
  if (resp.status !== 200) throw new Error(`CDP /json/version failed: ${resp.status}`);
  return resp.data.webSocketDebuggerUrl;
}

function cdpCommand(wsUrl, method, params = {}) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(wsUrl, { handshakeTimeout: 5000, perMessageDeflate: false });
    const id = 1;
    ws.on('open', () => {
      ws.send(JSON.stringify({ id, method, params }));
    });
    ws.on('message', (data) => {
      try {
        const msg = JSON.parse(data.toString());
        if (msg.id === id) {
          ws.close();
          if (msg.error) reject(new Error(JSON.stringify(msg.error)));
          else resolve(msg.result);
        }
      } catch (e) {}
    });
    ws.on('error', reject);
    setTimeout(() => { ws.close(); reject(new Error('CDP timeout')); }, 10000);
  });
}

async function main() {
  try {
    const wsUrl = await getBrowserCdpUrl();
    const result = await cdpCommand(wsUrl, 'Storage.getCookies', {});
    const cookies = result.cookies || [];
    const grokCookies = cookies.filter(c => c.domain.includes('grok.com') || c.domain.includes('x.ai'));
    console.log(`Total grok/x.ai cookies: ${grokCookies.length}`);
    for (const c of grokCookies) {
      console.log(`- ${c.name} (domain: ${c.domain}): ${c.value.substring(0, 30)}${c.value.length > 30 ? '...' : ''}`);
    }
  } catch (e) {
    console.error('Error:', e.message);
  }
}

main();

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

async function main() {
  try {
    const wsUrl = await getBrowserCdpUrl();
    console.log('Connecting to browser CDP:', wsUrl);
    const ws = new WebSocket(wsUrl, { handshakeTimeout: 5000, perMessageDeflate: false });
    
    ws.on('open', () => {
      console.log('✅ Connected to Edge debug session!');
      console.log('👉 Please send a chat message or refresh grok.com in the Edge browser...');
      
      // Enable Network tracking
      ws.send(JSON.stringify({
        id: 1,
        method: 'Network.enable',
        params: {}
      }));
    });
    
    ws.on('message', (data) => {
      try {
        const msg = JSON.parse(data.toString());
        if (msg.method === 'Network.requestWillBeSent') {
          const req = msg.params.request;
          const url = req.url;
          if (url.includes('/rest/app-chat/conversations/new') || url.includes('/conversations/new')) {
            console.log('\n🎯 CAPTURED GROK CHAT REQUEST!');
            console.log('URL:', url);
            console.log('Method:', req.method);
            console.log('\nHeaders:');
            console.log(JSON.stringify(req.headers, null, 2));
            if (req.postData) {
              console.log('\nPost Data:');
              console.log(req.postData);
            }
            console.log('\nClose script now.');
            ws.close();
            process.exit(0);
          }
        }
      } catch (e) {
        console.error('Error parsing message:', e);
      }
    });
    
    ws.on('error', (err) => {
      console.error('WS Error:', err);
    });
    
  } catch (e) {
    console.error('Error:', e.message);
  }
}

main();

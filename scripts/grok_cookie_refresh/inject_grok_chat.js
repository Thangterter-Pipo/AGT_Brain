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

async function getCdpTargets() {
  const resp = await httpReq('GET', `http://127.0.0.1:9515/json`);
  if (resp.status !== 200) throw new Error(`CDP /json failed: ${resp.status}`);
  return resp.data;
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function main() {
  try {
    const targets = await getCdpTargets();
    // Find Grok page tab
    const grokPage = targets.find(t => t.type === 'page' && t.url.includes('grok.com') && t.webSocketDebuggerUrl);
    
    if (!grokPage) {
      console.error('❌ Could not find an active Grok tab. Make sure grok.com is open in the debug Edge.');
      return;
    }
    
    console.log(`🎯 Found Grok tab: "${grokPage.title}" (${grokPage.url})`);
    console.log(`Connecting to page WS: ${grokPage.webSocketDebuggerUrl}`);
    
    const ws = new WebSocket(grokPage.webSocketDebuggerUrl, { handshakeTimeout: 5000, perMessageDeflate: false });
    
    ws.on('open', async () => {
      console.log('✅ Connected to page CDP!');
      
      // Enable Network and Runtime
      ws.send(JSON.stringify({ id: 1, method: 'Network.enable', params: {} }));
      ws.send(JSON.stringify({ id: 2, method: 'Runtime.enable', params: {} }));
      
      await sleep(1000);
      
      // Inject fetch request into the browser console
      console.log('🚀 Injecting fetch request into Grok tab console...');
      
      const fetchCode = `
        fetch('https://grok.com/rest/app-chat/conversations/new', {
          method: 'POST',
          headers: {
            'content-type': 'application/json',
          },
          body: JSON.stringify({
            message: 'Xin chào, test connection.',
            modelName: 'grok-4',
            modeId: 'grok-base',
            imageGenerationCount: 2,
            isAsyncChat: false,
            responseMetadata: {},
            returnImageBytes: false,
            returnRawGrokInXaiRequest: false,
            searchAllConnectors: false,
            sendFinalMetadata: true,
            temporary: true
          })
        })
        .then(r => r.text().then(text => ({ status: r.status, headers: [...r.headers.entries()], text })))
        .catch(e => ({ error: e.message }))
      `;
      
      ws.send(JSON.stringify({
        id: 3,
        method: 'Runtime.evaluate',
        params: {
          expression: fetchCode,
          awaitPromise: true,
          returnByValue: true
        }
      }));
    });
    
    ws.on('message', (data) => {
      try {
        const msg = JSON.parse(data.toString());
        
        // 1. Capture the network request sent by the browser
        if (msg.method === 'Network.requestWillBeSent') {
          const req = msg.params.request;
          if (req.url.includes('/rest/app-chat/conversations/new')) {
            console.log('\n==================================================');
            console.log('🎯 CAPTURED ACTUAL REQUEST HEADERS FROM EDGE CONSOLE:');
            console.log('==================================================');
            console.log(JSON.stringify(req.headers, null, 2));
            console.log('\n==================================================');
          }
        }
        
        // 2. Capture the fetch response returned from evaluate
        if (msg.id === 3) {
          console.log('\n==================================================');
          console.log('🏁 INJECTED FETCH RESPONSE RECEIVED:');
          console.log('==================================================');
          const result = msg.result.result;
          if (result.value) {
            console.log(JSON.stringify(result.value, null, 2));
          } else {
            console.log('Error/No value:', JSON.stringify(result, null, 2));
          }
          console.log('==================================================\n');
          ws.close();
          process.exit(0);
        }
      } catch (e) {
        console.error('Error parsing WS message:', e);
      }
    });
    
  } catch (e) {
    console.error('Error:', e.message);
  }
}

main();

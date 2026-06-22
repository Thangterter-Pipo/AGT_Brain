const http = require('http');
const fs = require('fs');
const path = require('path');
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

async function main() {
  try {
    const targets = await getCdpTargets();
    const grokPage = targets.find(t => t.type === 'page' && t.url.includes('grok.com') && t.webSocketDebuggerUrl);
    
    if (!grokPage) {
      console.error('❌ Could not find Grok tab.');
      return;
    }
    
    console.log(`Connecting to page WS: ${grokPage.webSocketDebuggerUrl}`);
    const ws = new WebSocket(grokPage.webSocketDebuggerUrl, { handshakeTimeout: 5000, perMessageDeflate: false });
    
    ws.on('open', () => {
      // Capture screenshot
      ws.send(JSON.stringify({
        id: 1,
        method: 'Page.captureScreenshot',
        params: {
          format: 'png'
        }
      }));
    });
    
    ws.on('message', (data) => {
      try {
        const msg = JSON.parse(data.toString());
        if (msg.id === 1) {
          if (msg.error) {
            console.error('Screenshot error:', msg.error);
          } else {
            const base64Data = msg.result.data;
            const buffer = Buffer.from(base64Data, 'base64');
            const outputPath = path.join(__dirname, 'edge_screenshot.png');
            fs.writeFileSync(outputPath, buffer);
            console.log(`✅ Screenshot saved to: ${outputPath}`);
          }
          ws.close();
          process.exit(0);
        }
      } catch (e) {
        console.error('Error parsing message:', e);
      }
    });
  } catch (e) {
    console.error('Error:', e.message);
  }
}

main();

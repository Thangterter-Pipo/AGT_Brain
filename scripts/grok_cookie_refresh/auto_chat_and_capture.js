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
    const grokPage = targets.find(t => t.type === 'page' && t.url.includes('grok.com') && t.webSocketDebuggerUrl);
    
    if (!grokPage) {
      console.error('❌ Could not find Grok tab.');
      return;
    }
    
    console.log(`Connecting to page WS: ${grokPage.webSocketDebuggerUrl}`);
    const ws = new WebSocket(grokPage.webSocketDebuggerUrl, { handshakeTimeout: 5000, perMessageDeflate: false });
    
    ws.on('open', async () => {
      console.log('✅ Connected to page CDP!');
      
      // Enable Network and Runtime
      ws.send(JSON.stringify({ id: 1, method: 'Network.enable', params: {} }));
      ws.send(JSON.stringify({ id: 2, method: 'Runtime.enable', params: {} }));
      
      await sleep(1000);
      
      // Inject script to type and submit chat
      console.log('🚀 Triggering chat submission via official UI components...');
      
      const injectSubmitChat = `
        (async () => {
          // Find textarea or contenteditable
          let inputEl = document.querySelector('textarea') || document.querySelector('[contenteditable="true"]');
          if (!inputEl) {
            // Try to find by placeholder
            const elList = document.querySelectorAll('*');
            for (const el of elList) {
              if (el.placeholder && el.placeholder.includes('Grok')) {
                inputEl = el;
                break;
              }
            }
          }
          
          if (!inputEl) {
            return { error: 'Could not find input element' };
          }
          
          console.log('Found input element:', inputEl.tagName);
          
          // Type message
          inputEl.focus();
          if (inputEl.tagName.toLowerCase() === 'textarea' || inputEl.tagName.toLowerCase() === 'input') {
            inputEl.value = 'Xin chào Grok';
            inputEl.dispatchEvent(new Event('input', { bubbles: true }));
            inputEl.dispatchEvent(new Event('change', { bubbles: true }));
          } else {
            inputEl.textContent = 'Xin chào Grok';
            inputEl.dispatchEvent(new Event('input', { bubbles: true }));
          }
          
          // Wait 500ms
          await new Promise(r => setTimeout(r, 500));
          
          // Find send button (usually follows textarea or has special icons)
          // Let's search for buttons near the input element
          let sendBtn = document.querySelector('button[type="submit"]') || document.querySelector('button svg')?.closest('button');
          if (!sendBtn) {
            // Fallback: look for button containing specific icons or attributes
            const buttons = document.querySelectorAll('button');
            for (const btn of buttons) {
              if (btn.outerHTML.includes('arrow') || btn.outerHTML.includes('send') || btn.getAttribute('aria-label') === 'Gửi') {
                sendBtn = btn;
                break;
              }
            }
          }
          
          if (sendBtn) {
            console.log('Clicking send button...');
            sendBtn.click();
            return { success: true, method: 'button_click' };
          } else {
            // Fallback: try pressing Enter
            console.log('Send button not found, trying to press Enter...');
            const enterEvent = new KeyboardEvent('keydown', {
              key: 'Enter',
              code: 'Enter',
              keyCode: 13,
              which: 13,
              bubbles: true,
              cancelable: true
            });
            inputEl.dispatchEvent(enterEvent);
            return { success: true, method: 'enter_key' };
          }
        })()
      `;
      
      ws.send(JSON.stringify({
        id: 3,
        method: 'Runtime.evaluate',
        params: {
          expression: injectSubmitChat,
          awaitPromise: true,
          returnByValue: true
        }
      }));
    });
    
    ws.on('message', (data) => {
      try {
        const msg = JSON.parse(data.toString());
        
        // 1. Capture the network request headers
        if (msg.method === 'Network.requestWillBeSent') {
          const req = msg.params.request;
          if (req.url.includes('/rest/app-chat/conversations/new')) {
            console.log('\n==================================================');
            console.log('🎯 CAPTURED OFFICIAL CHAT REQUEST HEADERS:');
            console.log('==================================================');
            console.log(JSON.stringify(req.headers, null, 2));
            console.log('\nPayload:');
            console.log(req.postData);
            console.log('==================================================\n');
            ws.close();
            process.exit(0);
          }
        }
        
        // 2. Capture evaluation result
        if (msg.id === 3) {
          console.log('Evaluate result:', JSON.stringify(msg.result.result, null, 2));
          // Don't close immediately, wait for the Network request
          setTimeout(() => {
            console.log('Timeout waiting for network request.');
            ws.close();
            process.exit(0);
          }, 5000);
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

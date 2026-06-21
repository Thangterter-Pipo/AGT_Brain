/**
 * Grok Cookie Auto-Refresh — Playwright Persistent Context
 * 
 * Flow:
 *   1. First run (--login): Opens grok.com in a VISIBLE browser → Bố logs in manually
 *      → Session is saved to ./browser_data/ (persistent context)
 *   2. Subsequent runs (--refresh): Opens headless browser with saved session
 *      → Extracts SSO cookie → Pushes to grok2api via Admin API
 *   3. Status check (--status): Shows current token status from grok2api
 * 
 * Usage:
 *   npm run login    — First time: open browser, login manually
 *   npm run refresh  — Auto-extract cookie and push to grok2api
 *   npm run status   — Check current token status
 */

const { chromium } = require('playwright');
const http = require('http');
const path = require('path');
const fs = require('fs');

// ═══════════════════════════════════════════
// Configuration
// ═══════════════════════════════════════════

const CONFIG = {
  // grok2api local server
  GROK2API_URL: process.env.GROK2API_URL || 'http://127.0.0.1:8000',
  GROK2API_ADMIN_KEY: process.env.GROK2API_ADMIN_KEY || 'grok2api',
  
  // Browser data directory (persistent session)
  BROWSER_DATA_DIR: path.join(__dirname, 'browser_data'),
  
  // Cookie log file
  COOKIE_LOG: path.join(__dirname, 'cookie_refresh.log'),
  
  // Grok.com target
  GROK_URL: 'https://grok.com',
  
  // Proxy (same as grok2api config)
  PROXY: process.env.GROK_PROXY || '',
  
  // Timeout for cookie extraction
  TIMEOUT_MS: 30000,
};

// ═══════════════════════════════════════════
// Utility
// ═══════════════════════════════════════════

function log(emoji, msg) {
  const ts = new Date().toISOString();
  const line = `[${ts}] ${emoji} ${msg}`;
  console.log(line);
  fs.appendFileSync(CONFIG.COOKIE_LOG, line + '\n');
}

function httpRequest(method, urlPath, body = null) {
  return new Promise((resolve, reject) => {
    const url = new URL(urlPath, CONFIG.GROK2API_URL);
    const options = {
      hostname: url.hostname,
      port: url.port,
      path: url.pathname + url.search,
      method,
      headers: {
        'Authorization': `Bearer ${CONFIG.GROK2API_ADMIN_KEY}`,
        'Content-Type': 'application/json',
      },
      timeout: 10000,
    };

    const req = http.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          resolve({ status: res.statusCode, data: JSON.parse(data) });
        } catch {
          resolve({ status: res.statusCode, data });
        }
      });
    });

    req.on('error', reject);
    req.on('timeout', () => { req.destroy(); reject(new Error('Request timeout')); });
    
    if (body) req.write(JSON.stringify(body));
    req.end();
  });
}

// ═══════════════════════════════════════════
// Core Functions
// ═══════════════════════════════════════════

/**
 * Step 1: Open browser for manual login (first time setup)
 */
async function loginFlow() {
  log('🔐', 'Opening browser for manual login to grok.com...');
  log('📌', `Browser data will be saved to: ${CONFIG.BROWSER_DATA_DIR}`);

  const launchOptions = {
    headless: false,
    channel: 'msedge', // Use Edge on Windows (available by default)
  };

  // Add proxy if configured
  if (CONFIG.PROXY) {
    launchOptions.proxy = { server: CONFIG.PROXY };
    log('🌐', `Using proxy: ${CONFIG.PROXY}`);
  }

  const context = await chromium.launchPersistentContext(
    CONFIG.BROWSER_DATA_DIR,
    {
      ...launchOptions,
      viewport: { width: 1280, height: 800 },
      userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
    }
  );

  const page = context.pages()[0] || await context.newPage();
  await page.goto(CONFIG.GROK_URL, { waitUntil: 'domcontentloaded' });

  log('👆', 'Please login to grok.com in the browser window.');
  log('⏳', 'Waiting for successful login (detecting SSO cookie)...');
  log('💡', 'After login, the browser will close automatically.');

  // Poll for SSO cookie
  let ssoToken = null;
  const maxWait = 5 * 60 * 1000; // 5 minutes
  const startTime = Date.now();

  while (Date.now() - startTime < maxWait) {
    const cookies = await context.cookies('https://grok.com');
    const ssoCookie = cookies.find(c => 
      c.name === 'sso' || 
      c.name === 'sso_rw' || 
      c.name.startsWith('sso')
    );

    if (ssoCookie && ssoCookie.value) {
      ssoToken = ssoCookie.value;
      log('✅', `SSO cookie found! Name: ${ssoCookie.name}, Value: ${ssoToken.substring(0, 16)}...`);
      break;
    }

    // Also check for auth-related cookies
    const authCookie = cookies.find(c =>
      c.name.includes('auth') ||
      c.name.includes('session') ||
      c.name.includes('token')
    );

    if (authCookie) {
      log('🔍', `Found auth cookie: ${authCookie.name} = ${authCookie.value.substring(0, 16)}...`);
    }

    await new Promise(r => setTimeout(r, 2000));
  }

  if (!ssoToken) {
    // Dump all cookies for debugging
    const allCookies = await context.cookies('https://grok.com');
    log('⚠️', `All grok.com cookies (${allCookies.length}):`);
    for (const c of allCookies) {
      log('  🍪', `${c.name} = ${c.value.substring(0, 20)}... (domain: ${c.domain})`);
    }
    log('❌', 'No SSO cookie found after 5 minutes. Check manually.');
  } else {
    // Push to grok2api
    await pushTokenToGrok2Api(ssoToken);
  }

  // Save all cookies to a local JSON backup
  const allCookies = await context.cookies();
  const cookieBackupPath = path.join(CONFIG.BROWSER_DATA_DIR, 'cookies_backup.json');
  fs.writeFileSync(cookieBackupPath, JSON.stringify(allCookies, null, 2));
  log('💾', `All cookies backed up to ${cookieBackupPath}`);

  await context.close();
  log('🔒', 'Browser closed. Session saved for future auto-refresh.');
}

/**
 * Step 2: Auto-refresh — extract cookie from saved session (headless)
 */
async function refreshFlow() {
  log('🔄', 'Auto-refreshing grok.com cookie (headless)...');

  if (!fs.existsSync(CONFIG.BROWSER_DATA_DIR)) {
    log('❌', 'No saved browser session found. Run "npm run login" first!');
    process.exit(1);
  }

  const launchOptions = {
    headless: true,
  };

  if (CONFIG.PROXY) {
    launchOptions.proxy = { server: CONFIG.PROXY };
  }

  const context = await chromium.launchPersistentContext(
    CONFIG.BROWSER_DATA_DIR,
    {
      ...launchOptions,
      viewport: { width: 1280, height: 800 },
      userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
    }
  );

  try {
    const page = context.pages()[0] || await context.newPage();
    
    // Navigate to grok.com to refresh cookies
    log('🌐', 'Navigating to grok.com to refresh session...');
    await page.goto(CONFIG.GROK_URL, { 
      waitUntil: 'domcontentloaded',
      timeout: CONFIG.TIMEOUT_MS,
    });

    // Wait a bit for cookies to settle
    await new Promise(r => setTimeout(r, 3000));

    // Check if we're still logged in
    const cookies = await context.cookies('https://grok.com');
    log('🍪', `Found ${cookies.length} cookies from grok.com`);

    // Look for SSO or auth cookies
    let ssoToken = null;
    for (const c of cookies) {
      if (c.name === 'sso' || c.name === 'sso_rw' || c.name.startsWith('sso')) {
        ssoToken = c.value;
        log('✅', `SSO cookie: ${c.name} = ${ssoToken.substring(0, 16)}...`);
        break;
      }
    }

    if (!ssoToken) {
      // Try broader search
      for (const c of cookies) {
        log('  🍪', `${c.name} = ${c.value.substring(0, Math.min(20, c.value.length))}...`);
      }
      log('⚠️', 'No SSO cookie found. Session may have expired. Run "npm run login" again.');
      
      // Try to extract from cookie backup
      const backupPath = path.join(CONFIG.BROWSER_DATA_DIR, 'cookies_backup.json');
      if (fs.existsSync(backupPath)) {
        const backup = JSON.parse(fs.readFileSync(backupPath, 'utf-8'));
        const ssoCookieBackup = backup.find(c => c.name === 'sso' || c.name === 'sso_rw');
        if (ssoCookieBackup) {
          log('🔄', 'Using SSO cookie from backup...');
          ssoToken = ssoCookieBackup.value;
        }
      }
    }

    if (ssoToken) {
      await pushTokenToGrok2Api(ssoToken);
    } else {
      log('❌', 'Failed to extract SSO cookie. Manual login required.');
      process.exit(1);
    }

    // Update cookie backup
    const allCookies = await context.cookies();
    const cookieBackupPath = path.join(CONFIG.BROWSER_DATA_DIR, 'cookies_backup.json');
    fs.writeFileSync(cookieBackupPath, JSON.stringify(allCookies, null, 2));

  } finally {
    await context.close();
  }
}

/**
 * Push SSO token to grok2api Admin API
 */
async function pushTokenToGrok2Api(ssoToken) {
  log('🚀', 'Pushing SSO token to grok2api...');

  try {
    // First, check current tokens
    const listResp = await httpRequest('GET', '/admin/api/tokens');
    
    if (listResp.status === 200 && listResp.data.tokens) {
      const existing = listResp.data.tokens;
      log('📊', `Current tokens in grok2api: ${existing.length}`);
      
      // Check if this token already exists
      const alreadyExists = existing.some(t => t.token === ssoToken);
      if (alreadyExists) {
        log('✅', 'Token already exists in grok2api. Skipping.');
        return;
      }
    }

    // Add the new token (pool=auto for auto-detection)
    const addResp = await httpRequest('POST', '/admin/api/tokens/add', {
      tokens: [ssoToken],
      pool: 'auto',
      tags: ['auto-refresh', new Date().toISOString().split('T')[0]],
    });

    if (addResp.status === 200) {
      log('✅', `Token added successfully! Response: ${JSON.stringify(addResp.data)}`);
    } else {
      log('❌', `Failed to add token: ${addResp.status} — ${JSON.stringify(addResp.data)}`);
    }
  } catch (err) {
    log('❌', `grok2api API error: ${err.message}`);
  }
}

/**
 * Check status of current tokens
 */
async function statusCheck() {
  log('📊', 'Checking grok2api token status...');

  try {
    const resp = await httpRequest('GET', '/admin/api/tokens');
    
    if (resp.status === 200 && resp.data.tokens) {
      const tokens = resp.data.tokens;
      console.log(`\n${'═'.repeat(60)}`);
      console.log(`  grok2api Token Status — ${tokens.length} token(s)`);
      console.log(`${'═'.repeat(60)}\n`);

      for (const t of tokens) {
        const masked = t.token.length > 20 
          ? `${t.token.substring(0, 8)}...${t.token.substring(t.token.length - 8)}`
          : t.token;
        console.log(`  Token:    ${masked}`);
        console.log(`  Pool:     ${t.pool}`);
        console.log(`  Status:   ${t.status}`);
        console.log(`  Uses:     ${t.use_count}`);
        console.log(`  Tags:     ${(t.tags || []).join(', ') || 'none'}`);
        
        if (t.quota) {
          for (const [mode, q] of Object.entries(t.quota)) {
            console.log(`  Quota ${mode}: ${q.remaining}/${q.total}`);
          }
        }
        console.log('');
      }
    } else {
      log('❌', `Status check failed: ${resp.status}`);
    }

    // Also check API health
    const modelsResp = await httpRequest('GET', '/v1/models');
    if (modelsResp.status === 200) {
      const models = modelsResp.data.data || [];
      log('✅', `grok2api healthy — ${models.length} models available`);
    }

  } catch (err) {
    log('❌', `Status check error: ${err.message}`);
  }
}

// ═══════════════════════════════════════════
// CLI
// ═══════════════════════════════════════════

async function main() {
  const args = process.argv.slice(2);
  const mode = args[0] || '--status';

  console.log(`\n🧠 Grok Cookie Auto-Refresh v1.0`);
  console.log(`   grok2api: ${CONFIG.GROK2API_URL}`);
  console.log(`   browser data: ${CONFIG.BROWSER_DATA_DIR}\n`);

  switch (mode) {
    case '--login':
    case 'login':
      await loginFlow();
      break;
    case '--refresh':
    case 'refresh':
      await refreshFlow();
      break;
    case '--status':
    case 'status':
      await statusCheck();
      break;
    default:
      console.log('Usage:');
      console.log('  node cookie_refresh.js --login    First time: open browser, login manually');
      console.log('  node cookie_refresh.js --refresh  Auto-extract cookie and push to grok2api');
      console.log('  node cookie_refresh.js --status   Check current token status');
  }
}

main().catch(err => {
  log('💥', `Fatal error: ${err.message}`);
  console.error(err);
  process.exit(1);
});

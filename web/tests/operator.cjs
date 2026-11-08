// Real Chromium + HTTP + durable journals. Workflow side effects are explicitly simulated.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const net = require('node:net');

(async () => {
  const repo = path.resolve(__dirname, '../..');
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'sf-operator-browser-'));
  const port = await new Promise(resolve => {
    const server = net.createServer().listen(0, '127.0.0.1', () => {
      const value = server.address().port; server.close(() => resolve(value));
    });
  });
  const origin = `http://127.0.0.1:${port}`;
  const server = spawn('uv', ['run', '--no-sync', 'python', 'tests/web_operator_fixture.py', temporary, String(port)],
    { cwd: repo, stdio: ['ignore', 'ignore', 'pipe'], env: process.env });
  let serverErrors = ''; server.stderr.on('data', chunk => { serverErrors += chunk.toString(); });
  let browser;
  try {
    for (let n = 0; n < 100; n++) {
      try { if ((await fetch(origin + '/api/health')).ok) break; } catch {}
      if (server.exitCode !== null) throw new Error('Browser fixture failed: ' + serverErrors);
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    browser = await chromium.launch({ headless: true,
      ...(process.env.SF_BROWSER_EXECUTABLE ? { executablePath: process.env.SF_BROWSER_EXECUTABLE } : {}) });
    const context = await browser.newContext();
    const page = await context.newPage();
    page.setDefaultTimeout(15000);
    const pageErrors = []; page.on('pageerror', e => pageErrors.push(e.message));
    await page.goto(fs.readFileSync(path.join(temporary, 'operator-link'), 'utf8'));
    const panel = page.locator('#operator');
    await panel.getByRole('button', { name: '次の1ステップを実行・再開', exact: true }).waitFor();
    assert(!page.url().includes('operator='), 'Capability must be removed from address bar');
    assert.equal(await page.evaluate(() => localStorage.length), 0);
    const advance = panel.getByRole('button', { name: '次の1ステップを実行・再開', exact: true });
    assert.equal(await advance.isEnabled(), false);
    await panel.getByLabel('表示した範囲のAI送信・隔離テスト・Issue/PR操作に同意する').check();
    assert.equal(await advance.isEnabled(), false, 'Bedrock consent must also be explicit');
    await panel.getByLabel('Bedrockの推論料金の発生に同意する').check();
    assert.equal(await advance.isEnabled(), true);
    let discarded = false; const requests = [];
    await page.route('**/api/operator/jobs', async route => {
      if (route.request().method() !== 'POST') return route.continue();
      requests.push(route.request().postDataJSON());
      if (!discarded) { discarded = true; await route.fetch(); await route.abort(); }
      else await route.continue();
    });
    await advance.click();
    await panel.getByRole('button', { name: '同じ送信を確認' }).waitFor();
    await panel.getByRole('button', { name: '同じ送信を確認' }).click();
    await panel.getByRole('button', { name: '停止を要求', exact: true }).waitFor();
    assert.equal(requests.length, 2);
    assert.equal(requests[0].request_id, requests[1].request_id, 'Unknown response must reuse nonce');
    assert.equal(await panel.getByRole('link', { name: 'PR ↗', exact: true }).count(), 1);
    assert((await panel.innerText()).includes('残り 31'));
    await page.reload();
    await panel.getByRole('button', { name: '停止を要求', exact: true }).waitFor();
    assert.equal(await advance.isEnabled(), false, 'Active job must prevent another submission');
    await panel.getByRole('button', { name: '停止を要求', exact: true }).click();
    await panel.getByText('停止または実行条件の確認が必要です', { exact: true }).waitFor();
    await panel.getByLabel('表示した範囲のAI送信・隔離テスト・Issue/PR操作に同意する').check();
    await panel.getByLabel('Bedrockの推論料金の発生に同意する').check();
    await advance.click();
    await panel.getByText('子PRのレビュー・マージ待ち', { exact: true }).waitFor();
    assert.notEqual(requests[1].request_id, requests[2].request_id);
    assert((await panel.innerText()).includes('残り 31'), 'Resume must not reset workflow budget');
    if (process.env.SF_BROWSER_DESKTOP_SCREENSHOT) {
      await page.setViewportSize({ width: 1280, height: 2400 });
      await page.locator('main').evaluate(e => { e.scrollTop = 0; });
      await panel.screenshot({ path: process.env.SF_BROWSER_DESKTOP_SCREENSHOT });
    }
    await page.setViewportSize({ width: 390, height: 844 });
    assert(await panel.evaluate(e => e.scrollWidth <= e.clientWidth + 1), 'Panel must fit mobile viewport');
    if (process.env.SF_BROWSER_SCREENSHOT) await panel.screenshot({ path: process.env.SF_BROWSER_SCREENSHOT });
    const anonymous = await browser.newContext();
    const guest = await anonymous.newPage(); await guest.goto(origin);
    await guest.locator('#operator').getByText('操作権限がありません。', { exact: false }).waitFor();
    await anonymous.close();
    await panel.getByRole('button', { name: '操作権限を閉じる' }).click();
    await panel.getByText('操作権限がありません。', { exact: false }).waitFor();
    assert.deepEqual(pageErrors, []);
    console.log('Operator browser checks passed: consent, fragment, idempotent retry, progress, stop, reload/resume, budgets, mobile, unauthorized access, logout.');
  } finally {
    if (browser) await browser.close();
    if (server.exitCode === null) {
      server.kill('SIGTERM');
      await new Promise(resolve => server.once('exit', resolve));
    }
    fs.rmSync(temporary, { recursive: true, force: true });
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });

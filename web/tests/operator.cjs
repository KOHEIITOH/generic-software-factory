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
    const projectRequests = []; const obsoleteRequests = [];
    page.on('request', request => {
      const pathname = new URL(request.url()).pathname;
      if (pathname.startsWith('/api/projects')) projectRequests.push(pathname);
      if (/^\/api\/(quick|github|runtimes|issues|runs)(\/|$)/.test(pathname)) obsoleteRequests.push(pathname);
    });
    const pageErrors = []; page.on('pageerror', e => pageErrors.push(e.message));
    await page.goto(fs.readFileSync(path.join(temporary, 'operator-link'), 'utf8'));
    const panel = page.locator('#operator');
    await panel.getByText('詳細設定・要件の分割・レビュー対応', { exact: true }).click();
    await panel.getByRole('button', { name: '次の1ステップを実行・再開', exact: true }).waitFor();
    assert(!page.url().includes('operator='), 'Capability must be removed from address bar');
    assert.equal(await page.evaluate(() => localStorage.length), 0);
    const advance = panel.getByRole('button', { name: '次の1ステップを実行・再開', exact: true });
    assert.equal(await advance.isEnabled(), false);
    await panel.getByRole('button', { name: '実行準備を確認', exact: true }).click();
    await panel.getByText('AI認証は未確認です。推論しません。', { exact: false }).waitFor();
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
    await panel.getByRole('button', { name: '計画案を作成・確認', exact: true }).click();
    await panel.getByRole('button', { name: '同じ送信を確認' }).waitFor();
    await panel.getByRole('button', { name: '同じ送信を確認' }).click();
    await panel.getByText('要件分割の計画・進捗', { exact: true }).click();
    const approve = panel.getByRole('button', { name: 'この計画を承認して子Issueを作成', exact: true });
    await approve.waitFor();
    assert.equal(await approve.isEnabled(), false);
    assert.equal(await panel.getByRole('link', { name: 'PR ↗', exact: true }).count(), 0);
    assert((await panel.innerText()).includes('add(2,3) returns 5'));
    assert((await panel.innerText()).includes('依存: first'));
    await panel.getByLabel('この計画・参照資料・変更範囲を確認し、子Issue作成を承認する').check();
    await approve.click();
    await panel.getByText('計画は承認済みです。次のステップで実装を進められます。', { exact: true }).waitFor();
    assert.equal(requests[2].action, 'approve');
    assert.equal(requests[2].confirm_bedrock, false);
    assert.match(requests[2].approved_plan, /^[a-f0-9]{64}$/);
    await panel.getByLabel('表示した範囲のAI送信・隔離テスト・Issue/PR操作に同意する').check();
    await panel.getByLabel('Bedrockの推論料金の発生に同意する').check();
    await advance.click();
    await panel.getByRole('button', { name: '停止を要求', exact: true }).waitFor();
    assert.equal(requests.length, 4);
    assert.equal(requests[0].request_id, requests[1].request_id, 'Unknown response must reuse nonce');
    assert.equal(await panel.getByRole('link', { name: 'PR ↗', exact: true }).count(), 1);
    assert((await panel.innerText()).includes('残り 31'));
    await panel.getByText('参照した要件資料・分割の根拠', { exact: true }).click();
    await panel.getByText('docs/requirements.md', { exact: true }).waitFor();
    assert((await panel.innerText()).includes('addition: docs/requirements.md → first'));
    assert(!(await panel.innerText()).includes('PRIVATE_'));
    assert((await panel.innerText()).includes('SHA256:'));
    await page.reload();
    await panel.getByText('要件分割の計画・進捗', { exact: true }).click();
    await panel.getByText('実行履歴・操作の証跡', { exact: true }).click();
    await panel.getByText('詳細設定・要件の分割・レビュー対応', { exact: true }).click();
    await panel.getByRole('button', { name: '停止を要求', exact: true }).waitFor();
    assert.equal(await advance.isEnabled(), false, 'Active job must prevent another submission');
    await panel.getByRole('button', { name: '停止を要求', exact: true }).click();
    await panel.getByText('停止または実行条件の確認が必要です', { exact: true }).waitFor();
    await panel.getByLabel('表示した範囲のAI送信・隔離テスト・Issue/PR操作に同意する').check();
    await panel.getByLabel('Bedrockの推論料金の発生に同意する').check();
    await advance.click();
    await panel.getByText('子PRのレビュー・マージ待ち', { exact: true }).waitFor();
    assert.notEqual(requests[3].request_id, requests[4].request_id);
    assert((await panel.innerText()).includes('残り 31'), 'Resume must not reset workflow budget');
    await panel.getByText('詳細設定・要件の分割・レビュー対応', { exact: true }).click();
    assert.equal(await panel.getByRole('button', { name: '同意して実行・Draft PR作成', exact: true }).isEnabled(), false);
    await panel.getByLabel('実行するIssue').selectOption('1');
    await panel.getByRole('button', { name: '同意して実行・Draft PR作成', exact: true }).click();
    await panel.getByRole('link', { name: 'Draft PRを開く ↗', exact: true }).first().waitFor();
    assert.equal(requests.at(-1).action, 'develop');
    assert.equal(requests.at(-1).issue_id, '1');
    assert.equal(requests.at(-1).confirm_run, true);
    assert.equal(requests.at(-1).confirm_bedrock, true);
    assert.equal(await panel.getByRole('link', { name: 'Draft PRを開く ↗', exact: true }).first().getAttribute('href'), 'https://github.com/fixture/repo/pull/99');
    await panel.getByText('要件分割の計画・進捗', { exact: true }).click();
    await panel.getByText('実行履歴・操作の証跡', { exact: true }).click();
    assert.equal(await page.locator('#workspace-details').getAttribute('open'), null, 'Optional Project management must be closed by default');
    assert.deepEqual(projectRequests, [], 'Normal execution must not fetch optional Project data');
    assert.deepEqual(obsoleteRequests, [], 'Normal execution must not call removed or duplicate APIs');
    for (const label of ['デモ用Draft PRを作成', 'このIssueを取り込む', 'Repositoryを紐付け', 'クイック開始', 'AI実装の事前チェック']) {
      assert(!(await page.locator('body').textContent()).includes(label), 'Obsolete control must be absent: ' + label);
    }
    await page.locator('#workspace-details > summary').click();
    await page.getByRole('button', { name: 'Projectを登録', exact: true }).waitFor();
    await page.getByLabel('新しいProject名', { exact: true }).fill('Browser Project');
    await page.getByRole('button', { name: 'Projectを登録', exact: true }).click();
    await page.getByText('Projectを登録しました。Repositoryを追加できます。', { exact: true }).waitFor();
    await page.getByLabel('Repositoryの場所', { exact: true }).fill('fixture/repo');
    await page.getByRole('button', { name: 'Repositoryを追加', exact: true }).click();
    await page.getByText('Repositoryを登録しました。', { exact: true }).waitFor();
    await page.locator('#workspace-details > summary').click();
    await page.locator('#workspace-details > summary').click();
    await page.getByLabel('Projectを選択', { exact: true }).selectOption({ label: 'Browser Project' });
    await page.locator('#projects .repository-row strong').filter({ hasText: 'fixture/repo' }).waitFor();
    await page.locator('#workspace-details > summary').click();
    if (process.env.SF_BROWSER_DESKTOP_SCREENSHOT) {
      await page.setViewportSize({ width: 1280, height: 2400 });
      await page.locator('main').evaluate(e => { e.scrollTop = 0; });
      await panel.screenshot({ path: process.env.SF_BROWSER_DESKTOP_SCREENSHOT });
    }
    await page.setViewportSize({ width: 390, height: 844 });
    assert(await panel.evaluate(e => e.scrollWidth <= e.clientWidth + 1), 'Panel must fit mobile viewport');
    await page.locator('#workspace-details > summary').click();
    await page.getByRole('button', { name: 'Projectを登録', exact: true }).waitFor();
    assert(await page.locator('body').evaluate(e => e.scrollWidth <= e.clientWidth + 1), 'Project management must fit mobile viewport');
    await page.locator('#workspace-details > summary').click();
    if (process.env.SF_BROWSER_SCREENSHOT) await panel.screenshot({ path: process.env.SF_BROWSER_SCREENSHOT });
    await panel.getByText('初回設定・Harness生成と改善', { exact: true }).click();
    await panel.getByLabel('セットアップのGitHub Repository選択', { exact: true }).selectOption('fixture/repo');
    await page.route('**/api/operator/setup/acquire', route => route.fulfill({
      status: 502, contentType: 'application/json',
      body: JSON.stringify({ detail: { code: 'scm_credentials_rejected' } }) }), { times: 1 });
    await panel.getByRole('button', { name: 'このRepositoryを取得して初回設定へ', exact: true }).click();
    await panel.getByText('GitHubが認証を拒否しました（401）', { exact: false }).waitFor();
    assert.equal(await panel.getByRole('button', { name: '設定とHarnessの案を作成', exact: true }).count(), 0);
    await panel.getByRole('button', { name: 'このRepositoryを取得して初回設定へ', exact: true }).click();
    await panel.getByText('GitHubから取得済み:', { exact: false }).waitFor();
    assert.equal(await panel.getByLabel('セットアップのRepositoryパス', { exact: true }).count(), 0, 'Remote setup must not require a host path');
    await panel.getByLabel('セットアップの設定名', { exact: true }).fill('Browser generated Harness');
    await panel.getByText('検証・実行イメージ・要件分割', { exact: true }).click();
    const imageInput = panel.getByLabel('セットアップの実行イメージ', { exact: true });
    const validImage = await imageInput.inputValue();
    await imageInput.fill('x'.repeat(70));
    await panel.getByRole('button', { name: '設定とHarnessの案を作成', exact: true }).click();
    await panel.getByText('設定案の作成：実行イメージは固定digest付きで指定してください', { exact: false }).waitFor();
    assert.equal(await panel.getByRole('button', { name: 'この設定とHarnessを登録', exact: true }).count(), 0);
    await imageInput.fill(validImage);
    await panel.getByLabel('セットアップの親Issue', { exact: true }).fill('0');
    await panel.getByRole('button', { name: '設定とHarnessの案を作成', exact: true }).click();
    await panel.getByText('入力を確認してください：親Issue番号（正の整数）', { exact: false }).waitFor();
    await panel.getByLabel('セットアップの親Issue', { exact: true }).fill('1');
    await panel.getByRole('button', { name: '設定とHarnessの案を作成', exact: true }).click();
    await panel.getByText('リポジトリを直接変更せず、以下の最小Project Harnessを生成します。', { exact: true }).waitFor();
    const install = panel.getByRole('button', { name: 'この設定とHarnessを登録', exact: true });
    assert.equal(await install.isEnabled(), false);
    await panel.getByLabel('この変更範囲・検証・Harnessを確認した', { exact: true }).check();
    await install.click();
    await panel.getByText('実行設定とHarnessを登録しました。Issueを選択して実行できます。', { exact: true }).waitFor();
    assert.equal(await panel.getByLabel('Repository', { exact: true }).locator('option:checked').innerText(), 'Browser generated Harness');
    assert.equal(fs.existsSync(path.join(fs.readFileSync(path.join(temporary, 'setup-root'), 'utf8'), 'AGENTS.md')), false, 'Generated Project Harness must not edit the source repository');
    assert(await panel.evaluate(e => e.scrollWidth <= e.clientWidth + 1), 'Setup must fit mobile viewport');
    const anonymous = await browser.newContext();
    const guest = await anonymous.newPage(); await guest.goto(origin);
    await guest.locator('#operator').getByText('操作権限がありません。', { exact: false }).waitFor();
    await anonymous.close();
    await panel.getByRole('button', { name: '操作権限を閉じる' }).click();
    await panel.getByText('操作権限がありません。', { exact: false }).waitFor();
    const operatorLink = fs.readFileSync(path.join(temporary, 'operator-link'), 'utf8');
    const submittedBeforeRecovery = requests.length;
    const reconnectInput = panel.getByLabel('再接続用の操作リンク', { exact: true });
    const reconnectButton = panel.getByRole('button', { name: '操作リンクで再接続', exact: true });
    await panel.getByRole('button', { name: '権限を再確認', exact: true }).click();
    await panel.getByText('操作権限がありません。', { exact: false }).waitFor();
    await reconnectInput.fill('https://evil.invalid/#operator=' + 'x'.repeat(43));
    await reconnectButton.click();
    await panel.getByText('起動したターミナルの、この画面と同じ接続先の操作リンクを貼り付けてください。', { exact: true }).waitFor();
    await reconnectInput.fill(origin + '/#operator=' + 'x'.repeat(43));
    await reconnectButton.click();
    await panel.getByText('操作リンクを確認してください。サーバー再起動後は新しいリンクが必要です。', { exact: true }).waitFor();
    assert.equal(await reconnectInput.inputValue(), '', 'Submitted capability must be cleared');
    await reconnectInput.fill(operatorLink); await reconnectButton.click();
    await panel.getByRole('button', { name: '操作権限を閉じる', exact: true }).waitFor();
    assert.equal(requests.length, submittedBeforeRecovery, 'Reauthentication must not submit or replay jobs');
    await panel.getByRole('button', { name: '操作権限を閉じる', exact: true }).click();
    await reconnectButton.waitFor();
    await page.evaluate(link => { window.location.hash = new URL(link).hash; }, operatorLink);
    await panel.getByRole('button', { name: '操作権限を閉じる', exact: true }).waitFor();
    assert(!page.url().includes('operator='), 'Same-tab recovery must remove the fragment');
    await context.clearCookies();
    await panel.getByRole('button', { name: 'Issue一覧を更新', exact: true }).click();
    await reconnectButton.waitFor();
    await reconnectInput.fill(operatorLink); await reconnectButton.click();
    await panel.getByRole('button', { name: '操作権限を閉じる', exact: true }).waitFor();
    assert.equal(requests.length, submittedBeforeRecovery);
    assert.equal(await page.evaluate(() => localStorage.length + sessionStorage.length), 0);
    const failedContext = await browser.newContext();
    const failedPage = await failedContext.newPage();
    await failedPage.goto(origin + '/#operator=' + 'z'.repeat(43));
    await failedPage.getByLabel('再接続用の操作リンク', { exact: true }).fill(operatorLink);
    await failedPage.getByRole('button', { name: '操作リンクで再接続', exact: true }).click();
    await failedPage.getByRole('button', { name: '操作権限を閉じる', exact: true }).waitFor();
    await failedContext.close();
    assert.deepEqual(pageErrors, []);
    console.log('Operator browser checks passed: Issue selection + single execute-and-consent button to Draft PR, no obsolete controls/API requests, lazy Project management/reopen, Web setup with generated Project Harness + exact approval, collapsed history, consent, fragment, idempotent retry, reviewed plan approval, progress, requirement source metadata/citations, stop, reload/resume, budgets, mobile, unauthorized access, logout + failed-login retry + same-tab fragment recovery + expired-cookie recovery without job replay.');
  } finally {
    if (browser) await browser.close();
    if (server.exitCode === null) {
      server.kill('SIGTERM');
      await new Promise(resolve => server.once('exit', resolve));
    }
    fs.rmSync(temporary, { recursive: true, force: true });
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });

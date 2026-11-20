// 冒烟：制作台对话发送后必须有可见回复（messages 渲染回归）
const { chromium } = require('../prototype/node_modules/playwright-core');
(async () => {
  const browser = await chromium.launch({ channel: 'chrome' });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('console', m => {
    if (m.type() === 'error' && !m.text().includes('404')) errors.push('console: ' + m.text());
  });
  await page.goto('http://localhost:1420/#/', { waitUntil: 'networkidle' });
  await page.waitForTimeout(800);
  console.log('引擎连接:', await page.locator('.status').innerText().catch(() => 'N/A'));
  // 直接进真实项目（首页的 .proj 点击走占位路由 /p/current，是既有导航问题）
  await page.goto('http://localhost:1420/#/p/01M7VSCHV5CKQ0STARN3QPS7H4', { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);
  console.log('路由:', new URL(page.url()).hash);
  // 在对话输入框发送消息
  const input = page.locator('input[aria-label="给助手的留言"]');
  if (!await input.count()) { console.log('FAIL: 找不到对话输入框'); await browser.close(); process.exit(1); }
  await input.fill('第二集节奏太快了');
  await input.press('Enter');
  await page.waitForTimeout(1200);
  const userMsgs = await page.locator('.chat-msg.user').count();
  const agentMsgs = await page.locator('.chat-msg.agent').count();
  const agentText = agentMsgs ? await page.locator('.chat-msg.agent .chat-text').first().innerText() : '';
  console.log('用户消息数:', userMsgs, '| 助手消息数:', agentMsgs);
  console.log('助手回复:', agentText);
  const intentBar = await page.locator('.intent-bar').count();
  console.log('意图确认条:', intentBar);
  const ok = userMsgs >= 1 && agentMsgs >= 1 && agentText.length > 0;
  console.log(errors.length ? 'JS错误: ' + errors.join(' | ') : 'JS错误: 无');
  console.log(ok && !errors.length ? '=== PASS ===' : '=== FAIL ===');
  await browser.close();
  process.exit(ok && !errors.length ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });

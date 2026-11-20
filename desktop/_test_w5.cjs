const { chromium } = require('../prototype/node_modules/playwright-core');
(async () => {
  const browser = await chromium.launch({ channel: 'chrome' });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push('console:' + m.text()); });
  await page.goto('http://127.0.0.1:8766/index.html', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);
  console.log('连接:', await page.locator('.status').innerText());
  // 创建项目
  await page.fill('textarea', '测试 W5：一个普通人的一生，从八岁到七十岁，三集竖屏短剧');
  await page.getByRole('button', { name: '开始创作' }).click();
  await page.waitForTimeout(600);
  // 充值到足够 12 镜头
  await page.locator('.balance').click(); await page.waitForTimeout(150);
  await page.locator('.plan', { hasText: '创作月包' }).click();
  await page.getByRole('button', { name: '确认支付' }).click(); await page.waitForTimeout(600);
  console.log('=== 真实生成进度 ===');
  await page.locator('.side .st').nth(4).click(); await page.waitForTimeout(150);
  await page.getByRole('button', { name: '按这个方案生成' }).click();
  await page.waitForTimeout(1200);
  const label = await page.locator('.card-hd .pill').innerText();
  const pct = await page.locator('.big-num').innerText();
  console.log('进度标签:', label, '| 百分比:', pct);
  console.log('真实模式:', !(await page.locator('.chip', { hasText: '跳过等待' }).count()));
  console.log('引擎行数:', await page.locator('.table tbody tr').count());
  // 暂停后进度冻结
  const pauseBtn = page.getByRole('button', { name: '暂停生成' });
  if (await pauseBtn.count()) {
    await pauseBtn.click(); await page.waitForTimeout(150);
    const before = await page.locator('.card-hd .pill').innerText();
    await page.waitForTimeout(1000);
    const after = await page.locator('.card-hd .pill').innerText();
    console.log('暂停冻结:', before, '->', after, before === after ? 'OK' : 'FAIL');
    await page.getByRole('button', { name: '继续生成' }).click();
  }
  console.log('=== SSE 对话 + 意图确认门 ===');
  const msg = page.locator('input[aria-label="给助手的留言"]');
  await msg.fill('第二集太快了，加点铺垫');
  await msg.press('Enter');
  await page.waitForTimeout(1400);
  console.log('有确认条:', await page.locator('.intent-bar').count() > 0);
  console.log('确认文案:', (await page.locator('.ib-txt').innerText().catch(() => '无')).slice(0, 70));
  const cancelBtn = page.getByRole('button', { name: '取消' });
  if (await cancelBtn.count()) {
    await cancelBtn.click(); await page.waitForTimeout(150);
    console.log('取消后确认条:', await page.locator('.intent-bar').count());
  }
  console.log('=== 错误 ===');
  console.log('errors:', errors.length ? errors.slice(0, 5) : '无');
  await browser.close();
})();

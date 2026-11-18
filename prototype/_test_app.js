const { chromium } = require('playwright-core');
const path = require('path');
(async () => {
  const browser = await chromium.launch({ channel: 'chrome' });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push('CONSOLE: ' + m.text()); });
  const url = 'file:///' + path.resolve('漫剧工场-制作台-v5.0.html').replace(/\\/g, '/');
  await page.goto(url);
  await page.waitForTimeout(500);
  const log = [];
  const shot = async (name) => { await page.screenshot({ path: `_v_${name}.png` }); };
  const clickText = async (txt) => {
    const btn = page.getByRole('button', { name: txt, exact: false }).first();
    if (await btn.count()) { await btn.click({ timeout: 4000 }); }
    else { await page.locator(`text=${txt}`).first().click({ timeout: 4000 }); }
    await page.waitForTimeout(350);
  };
  // 1. 侧栏 8 步逐一点击
  for (let i = 1; i <= 8; i++) {
    await page.locator('.side .st').nth(i - 1).click();
    await page.waitForTimeout(220);
    const title = await page.locator('.card-hd').first().innerText();
    log.push(`步骤${i}: ${title.split('\n')[0]}`);
  }
  await shot('step8');
  // 2. 回到第 1 步，测试重新生成 / 确认
  await page.locator('.side .st').nth(0).click();
  await clickText('重新生成这一稿');
  log.push('重新生成: ' + (await page.locator('.card-hd .pill').first().innerText()));
  await clickText('确认这一稿，去定角色');
  log.push('确认后步骤标题: ' + (await page.locator('.card-hd').first().innerText()).split('\n')[0]);
  // 3. 剧本确认 → 角色
  await clickText('确认剧本，开始定角色');
  await page.waitForTimeout(250);
  await shot('roles');
  // 4. 角色点选
  const before = await page.locator('.role.sel').count();
  await page.locator('.role').first().click();
  await page.waitForTimeout(200);
  const after = await page.locator('.role.sel').count();
  log.push(`角色选择: ${before} -> ${after}`);
  await page.locator('.role').first().click();
  await clickText('确认这 5 个角色');
  await page.waitForTimeout(250);
  await shot('lock');
  // 5. 锁定弹窗
  await clickText('确认形象，开始拆镜头');
  await page.waitForTimeout(300);
  const modalOpen = await page.locator('#modal.open').count();
  log.push('锁定弹窗打开: ' + (modalOpen === 1));
  await shot('modal');
  await clickText('再看看');
  const modalClosed = await page.locator('#modal.open').count();
  log.push('弹窗关闭: ' + (modalClosed === 0));
  await clickText('确认形象，开始拆镜头');
  await clickText('确认形象，继续');
  await page.waitForTimeout(300);
  log.push('锁定后步骤: ' + (await page.locator('.card-hd').first().innerText()).split('\n')[0]);
  await shot('locked');
  // 6. 拆镜头 → 开始生成
  await clickText('按这个方案生成');
  await page.waitForTimeout(2500);
  const pct1 = await page.locator('.big-num').first().innerText();
  log.push('生成中进度: ' + pct1);
  await shot('gen');
  await clickText('暂停生成');
  await page.waitForTimeout(700);
  const pct2 = await page.locator('.big-num').first().innerText();
  log.push('暂停后进度(应不变): ' + pct2);
  await clickText('跳过等待，直接完成');
  await page.waitForTimeout(400);
  log.push('完成后: ' + (await page.locator('.card-hd .pill').first().innerText()));
  await shot('gendone');
  // 7. 看成片 → 播放
  console.log('BEFORE WATCH, card:', (await page.locator('.card-hd').first().innerText()).replace(/\n/g,' | '));
  console.log('buttons:', await page.locator('.btn').allInnerTexts());
  await clickText('看前 30 秒');
  await page.waitForTimeout(400);
  console.log('AFTER WATCH, card:', (await page.locator('.card-hd').first().innerText()).replace(/\n/g,' | '));
  await shot('watch');
  await page.locator('.playbtn').click();
  await page.waitForTimeout(1200);
  const t1 = await page.locator('.ptime span').first().innerText();
  log.push('播放时间: ' + t1);
  await page.locator('.playbtn').click();
  await page.waitForTimeout(300);
  await clickText('重新生成这一段');
  // 8. 导出
  await clickText('导出整集');
  await page.waitForTimeout(250);
  await clickText('开始导出');
  await page.waitForTimeout(2600);
  const hasDownload = await page.locator('text=下载视频').count();
  log.push('导出后出现下载按钮: ' + (hasDownload > 0));
  await shot('export');
  if (hasDownload > 0) { await clickText('下载视频'); }
  // 9. 右栏三个页签
  for (const t of ['角色', '花费', '镜头']) {
    await page.locator('#rtabs button', { hasText: t }).click();
    await page.waitForTimeout(200);
    log.push(`页签${t}: ${(await page.locator('#rbody').innerText()).slice(0, 24).replace(/\n/g, ' / ')}`);
  }
  // 10. 模型设置：切选项 + 测试连接 + 保存
  await page.locator('.seg button', { hasText: '模型设置' }).click();
  await page.waitForTimeout(300);
  await shot('settings');
  await page.locator('#settingsBody .ch').nth(1).click();
  await page.waitForTimeout(200);
  const keyrow = await page.locator('#settingsBody .keyrow').count();
  log.push('切到自带密钥后出现密钥输入: ' + (keyrow > 0));
  if (keyrow > 0) await clickText('测试连接');
  await clickText('保存设置');
  // 11. 深色模式
  await page.locator('.seg button', { hasText: '制作' }).click();
  await page.waitForTimeout(200);
  await page.locator('#themeBtn').click();
  await page.waitForTimeout(400);
  const theme = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
  log.push('深色模式: ' + theme);
  await shot('dark');
  // 12. 输入框发送
  await page.locator('#msg').fill('第二集太快了');
  await page.locator('#msg').press('Enter');
  await page.waitForTimeout(300);
  const toastTxt = await page.locator('#toast').innerText();
  log.push('发送反馈: ' + toastTxt);
  console.log('--- 交互验证 ---');
  log.forEach(l => console.log(l));
  console.log('--- 错误 ---');
  console.log(errors.length ? errors.join('\n') : '无 JS 错误');
  await browser.close();
})();

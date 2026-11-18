const { chromium } = require('playwright-core');
const path = require('path');
(async () => {
  const browser = await chromium.launch({ channel: 'chrome' });
  const errors = [];
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push('CONSOLE: ' + m.text()); });
  const file = 'file:///' + path.resolve('鲸鲨漫剧-制作台-v2.0.html').replace(/\\/g, '/');
  await page.goto(file);
  await page.waitForTimeout(400);
  const shot = async n => page.screenshot({ path: `_w_${n}.png` });
  const clickText = async txt => {
    const b = page.getByRole('button', { name: txt, exact: false }).first();
    if (await b.count()) await b.click({ timeout: 4000 });
    else await page.locator(`text=${txt}`).first().click({ timeout: 4000 });
    await page.waitForTimeout(250);
  };
  console.log('=== 首页 ===');
  console.log('默认视图:', await page.evaluate(() => document.querySelector('.view.on').id));
  await page.fill('#idea', '');
  await page.locator('.chip', { hasText: '都市逆袭' }).click();
  const filled = await page.inputValue('#idea');
  console.log('模板填充:', filled.slice(0, 12) + '…');
  await page.locator('.chip', { hasText: '普通人的一生' }).click();
  await page.getByRole('button', { name: '开始创作' }).click();
  await page.waitForTimeout(250);
  console.log('创建后视图:', await page.evaluate(() => document.querySelector('.view.on').id),
    '| 步骤:', (await page.locator('.card-hd').first().innerText()).split('\n')[0]);
  await page.locator('.seg button', { hasText: '首页' }).click();
  await page.waitForTimeout(150);
  await page.locator('.proj').first().click();
  await page.waitForTimeout(150);
  console.log('继续上次视图:', await page.evaluate(() => document.querySelector('.view.on').id),
    '| crumb:', await page.locator('#crumb').innerText());
  console.log('品牌:', await page.locator('.brand .nm').innerText());
  // 业务闭环：充值 → 作品库
  console.log('=== 业务闭环 ===');
  await page.locator('.balance').click();
  await page.waitForTimeout(200);
  console.log('充值弹窗:', await page.evaluate(() => document.querySelector('#pay').classList.contains('open')));
  await page.locator('.plan', { hasText: '创作月包' }).click();
  await page.waitForTimeout(100);
  await page.getByRole('button', { name: '确认支付' }).click();
  await page.waitForTimeout(200);
  console.log('充值后额度:', await page.locator('.balance b').innerText());
  await page.locator('.seg button', { hasText: '作品库' }).click();
  await page.waitForTimeout(200);
  console.log('作品库视图:', await page.evaluate(() => document.querySelector('.view.on').id),
    '| 成片卡数:', await page.locator('.workcard').count(),
    '| crumb:', await page.locator('#crumb').innerText());
  await page.locator('.workcard').first().locator('.btn', { hasText: '复制发布文案' }).click();
  await page.waitForTimeout(150);
  await page.locator('.seg button', { hasText: '首页' }).click();
  await page.waitForTimeout(150);
  console.log('首页项目卡数:', await page.locator('.proj').count());
  console.log('=== 制作台 ===');
  await page.locator('.seg button', { hasText: '制作' }).click();
  await page.waitForTimeout(150);
  console.log('初始主题:', await page.evaluate(() => document.documentElement.getAttribute('data-theme')));
  // 8 步逐一点击
  const titles = [];
  for (let i = 0; i < 8; i++) {
    await page.locator('.side .st').nth(i).click();
    await page.waitForTimeout(150);
    titles.push(await page.locator('.card-hd').first().innerText());
  }
  console.log('八步标题:', titles.map(t => t.split('\n')[0]).join(' | '));
  if (!titles.every(t => t.includes('第'))) throw new Error('步骤标题异常');
  // 回到第1步：重写剧本、确认
  await page.locator('.side .st').nth(0).click();
  await page.waitForTimeout(150);
  await clickText('重新生成这一稿');
  console.log('稿号:', await page.locator('.card-hd .pill').first().innerText());
  await clickText('确认这一稿');
  console.log('确认后步骤:', (await page.locator('.card-hd').first().innerText()).split('\n')[0]);
  await clickText('确认剧本，开始定角色');
  console.log('角色页:', (await page.locator('.card-hd').first().innerText()).split('\n')[0]);
  // 角色多选
  const before = await page.locator('.role.sel').count();
  await page.locator('.role').nth(4).click();
  await page.waitForTimeout(150);
  const after = await page.locator('.role.sel').count();
  console.log('角色选中数:', before, '->', after);
  if (before === after) throw new Error('角色选择未生效');
  await clickText('确认这');
  console.log('锁定页:', (await page.locator('.card-hd').first().innerText()).split('\n')[0]);
  // 锁定弹窗
  await clickText('确认形象，开始拆镜头');
  console.log('弹窗打开:', await page.locator('#modal').evaluate(e => e.classList.contains('open')));
  await shot('modal');
  await clickText('确认形象，继续');
  console.log('拆分镜头页:', (await page.locator('.card-hd').first().innerText()).split('\n')[0]);
  // 生成
  await clickText('按这个方案生成');
  console.log('生成页:', (await page.locator('.card-hd').first().innerText()).split('\n')[0]);
  await page.waitForTimeout(1200);
  const p1 = await page.locator('.big-num').innerText();
  await clickText('暂停生成');
  await page.waitForTimeout(1000);
  const p2 = await page.locator('.big-num').innerText();
  console.log('暂停进度:', p1, '->', p2);
  if (p1 !== p2) throw new Error('暂停未生效');
  await clickText('继续生成');
  await clickText('跳过等待，直接完成');
  console.log('完成进度:', await page.locator('.big-num').innerText());
  await shot('gen');
  // 播放
  await clickText('看前 30 秒');
  console.log('成片页:', (await page.locator('.card-hd').first().innerText()).split('\n')[0]);
  await clickText('播放');
  await page.waitForTimeout(700);
  console.log('播放计时:', await page.locator('.ptime span').first().innerText());
  await shot('watch');
  // 导出
  await clickText('导出整集');
  await clickText('开始导出');
  await page.waitForTimeout(2400);
  console.log('导出状态:', await page.locator('.card-hd .pill').innerText());
  await clickText('下载视频');
  // 右栏页签
  for (const t of ['角色', '花费', '镜头']) {
    await page.locator('#rtabs button', { hasText: t }).click();
    await page.waitForTimeout(120);
  }
  console.log('右栏页签: OK');
  // 设置页
  await page.locator('.seg button', { hasText: '模型设置' }).click();
  await page.waitForTimeout(150);
  console.log('设置组数:', await page.locator('#settingsBody .grp').count());
  await page.locator('#settingsBody .ch').nth(1).click();
  await page.waitForTimeout(120);
  console.log('密钥输入框:', await page.locator('#settingsBody .keyrow').count());
  await clickText('测试连接');
  await clickText('保存设置');
  await shot('settings');
  // 平面默认确认
  console.log('默认平面:', await page.evaluate(() => document.body.classList.contains('flat')));
  // 主题
  await page.locator('.seg button', { hasText: '制作' }).click();
  await page.locator('.side .st').nth(2).click();
  await page.locator('#themeBtn').click();
  await page.waitForTimeout(200);
  console.log('切换后主题:', await page.evaluate(() => document.documentElement.getAttribute('data-theme')));
  await shot('light');
  await page.locator('#themeBtn').click();
  await page.waitForTimeout(200);
  await shot('dark');
  // 1024 视口
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.waitForTimeout(300);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  console.log('1024 横向溢出:', overflow);
  await shot('1024');
  console.log('JS 错误:', errors.length ? errors.join(' | ') : '无');
  // 官网
  const site = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const serr = [];
  site.on('pageerror', e => serr.push(e.message));
  await site.goto('file:///' + path.resolve('鲸鲨漫剧-官网-v2.0.html').replace(/\\/g, '/'));
  await site.waitForTimeout(1200);
  console.log('=== 官网 ===');
  console.log('标题:', await site.title());
  console.log('步骤卡:', await site.locator('.step-cell').count(), '规格卡:', await site.locator('.spec').count());
  await site.locator('#themeBtn').click();
  await site.waitForTimeout(200);
  console.log('官网切换后主题:', await site.evaluate(() => document.documentElement.getAttribute('data-theme')));
  await site.locator('#themeBtn').click();
  await site.waitForTimeout(200);
  await site.screenshot({ path: '_w_site.png' });
  await site.evaluate(() => document.querySelector('#steps').scrollIntoView());
  await site.waitForTimeout(900);
  await site.screenshot({ path: '_w_site_steps.png' });
  console.log('官网 JS 错误:', serr.length ? serr.join(' | ') : '无');
  await browser.close();
  if (errors.length || serr.length || overflow) process.exit(1);
})().catch(e => { console.error('FAILED:', e.message); process.exit(1); });

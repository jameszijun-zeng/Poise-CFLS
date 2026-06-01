// 稳盈 / Poise · 5 分钟 demo 自动化驱动
//
// 用法：
//   1. 启动屏幕录制（QuickTime / OBS / ScreenFlow），分辨率建议 1920×1080
//   2. node scripts/demo_runner.js
//   3. 等约 5 分钟，自动播完
//   4. 停止录制
//
// 前置：
//   - 全栈已启动（make up）
//   - 已 bootstrap 默认用户（make seed）
//   - 已配置 DEEPSEEK_API_KEY（chat 段需要）
//
// 调试模式（不操作浏览器，仅打印步骤）：
//   DEMO_DRY_RUN=1 node scripts/demo_runner.js

const puppeteer = require("puppeteer");

const DRY = !!process.env.DEMO_DRY_RUN;
const BASE = process.env.WEB_BASE || "http://localhost:3000";
const USER = process.env.DEMO_USER || "treasurer";
const PASS = process.env.DEMO_PASS || "Poise@2026";

// 节奏控制（毫秒）—— 与 doc/Demo录制脚本_5分钟.md 对齐
const SHORT = 800;     // 短停顿，让观众跟上鼠标
const MED = 1800;      // 中停顿，让画面定格
const LONG = 3200;     // 长停顿，关键画面
const READ = 5000;     // 阅读停顿，给文字时间

const log = (s) => console.log(`[${new Date().toISOString().slice(11, 19)}] ${s}`);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// 让鼠标缓慢移动到目标，便于观众跟随
async function smoothMove(page, x, y, steps = 25) {
  await page.mouse.move(x, y, { steps });
}

// 按文本找按钮并点击
async function clickByText(page, text, opts = {}) {
  const handle = await page.evaluateHandle((t) => {
    const all = [...document.querySelectorAll("button, a, [role=button]")];
    return all.find((el) => el.textContent.includes(t));
  }, text);
  const el = handle.asElement();
  if (!el) throw new Error(`找不到按钮: ${text}`);
  const box = await el.boundingBox();
  if (box) {
    await smoothMove(page, box.x + box.width / 2, box.y + box.height / 2);
    await sleep(opts.preDelay ?? SHORT);
  }
  await el.click();
}

// 点击侧边栏导航项
async function navTo(page, label, urlHint) {
  log(`▶ 导航 → ${label}`);
  await clickByText(page, label, { preDelay: SHORT });
  if (urlHint) {
    await page.waitForFunction(
      (u) => location.pathname.includes(u),
      { timeout: 8000 },
      urlHint,
    );
  }
  await sleep(MED);
}

async function typeSlowly(page, selector, text, delayMs = 35) {
  const el = await page.$(selector);
  await el.click();
  await page.keyboard.type(text, { delay: delayMs });
}

// 等待页面内出现某段文本
async function waitForText(page, text, timeout = 60000) {
  await page.waitForFunction(
    (t) => document.body.innerText.includes(t),
    { timeout },
    text,
  );
}

// ====================================================================
// 主流程
// ====================================================================
(async () => {
  const t0 = Date.now();
  log(`开始 demo · DRY=${DRY ? "ON（仅打印）" : "OFF"}`);
  log(`目标 URL = ${BASE}`);

  if (DRY) {
    log("DRY 模式：跳过浏览器启动");
    log("流程预演：");
    [
      "0:00-0:20 开场：浏览器对准 /login",
      "0:20-1:00 登录 → 数据录入页浏览",
      "1:00-2:00 13 周看板 → 触发预测 → 看图 → 看表",
      "2:00-3:00 方案对比 → 触发求解 → 看 3 卡 → what-if 抽屉",
      "3:00-4:15 对话参谋 → 两条问题（含连环 tool）",
      "4:15-4:45 MAPE 看板 → 手动触发滚动",
      "4:45-5:00 致谢页（fade）",
    ].forEach((s) => log("  · " + s));
    log("DRY 完成，耗时 " + ((Date.now() - t0) / 1000).toFixed(1) + "s");
    return;
  }

  const browser = await puppeteer.launch({
    headless: false,
    defaultViewport: null,
    args: [
      "--window-size=1920,1080",
      "--window-position=0,0",
      "--start-fullscreen",
    ],
  });
  const page = await browser.pages().then((p) => p[0] || browser.newPage());
  await page.setViewport({ width: 1920, height: 1080 });

  try {
    // ============== 0:00 - 0:20 ==============
    log("=== 0:00-0:20 开场：打开登录页 ===");
    await page.goto(`${BASE}/login`, { waitUntil: "networkidle2" });
    await sleep(LONG);

    // ============== 0:20 - 1:00 ==============
    log("=== 0:20-1:00 登录 + 数据录入 ===");
    await typeSlowly(page, 'input[id="username"]', USER, 60);
    await sleep(SHORT);
    await typeSlowly(page, 'input[id="password"]', PASS, 40);
    await sleep(SHORT);
    await clickByText(page, "登录");
    await page.waitForFunction(
      () => location.pathname.includes("dashboard"),
      { timeout: 10000 },
    );
    await sleep(MED);

    // 概览页停留
    log("停留概览页");
    await sleep(LONG);
    // 平滑滚动一下，让观众看到 3 张卡
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
    await sleep(MED);

    // 进数据录入
    await navTo(page, "数据录入", "/data");
    await waitForText(page, "13 周现金流项", 15000);
    log("滚动展示数据表");
    await page.evaluate(async () => {
      window.scrollTo({ top: 0, behavior: "smooth" });
      await new Promise((r) => setTimeout(r, 1500));
      window.scrollTo({ top: 800, behavior: "smooth" });
      await new Promise((r) => setTimeout(r, 2500));
      window.scrollTo({ top: 1600, behavior: "smooth" });
      await new Promise((r) => setTimeout(r, 2500));
      window.scrollTo({ top: 2400, behavior: "smooth" });
      await new Promise((r) => setTimeout(r, 2500));
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
    await sleep(MED);

    // ============== 1:00 - 2:00 ==============
    log("=== 1:00-2:00 13 周预测看板 ===");
    await navTo(page, "13 周看板", "/forecast");
    await sleep(SHORT);
    // 触发预测
    log("触发「重新预测」");
    try {
      await clickByText(page, "重新预测");
    } catch {
      await clickByText(page, "生成首份预测");
    }
    await sleep(LONG);

    log("展示 4 张顶部卡 + 2 张图");
    await page.evaluate(async () => {
      window.scrollTo({ top: 0, behavior: "smooth" });
      await new Promise((r) => setTimeout(r, 2500));
      window.scrollTo({ top: 600, behavior: "smooth" });
      await new Promise((r) => setTimeout(r, 4500));
      window.scrollTo({ top: 1300, behavior: "smooth" });
      await new Promise((r) => setTimeout(r, 4500));
      window.scrollTo({ top: 2200, behavior: "smooth" });
      await new Promise((r) => setTimeout(r, 4000));
    });
    await sleep(MED);

    // ============== 2:00 - 3:00 ==============
    log("=== 2:00-3:00 方案对比 + what-if ===");
    await navTo(page, "方案对比", "/plans");
    await sleep(SHORT);
    log("触发「重新求解」");
    try {
      await clickByText(page, "重新求解");
    } catch (e) {
      log("未找到重新求解按钮 —— 可能页面状态不对");
    }
    await sleep(LONG);

    log("展示 3 档卡片");
    await page.evaluate(async () => {
      window.scrollTo({ top: 0, behavior: "smooth" });
      await new Promise((r) => setTimeout(r, 3000));
      window.scrollTo({ top: 500, behavior: "smooth" });
      await new Promise((r) => setTimeout(r, 4000));
      window.scrollTo({ top: 1200, behavior: "smooth" });
      await new Promise((r) => setTimeout(r, 3500));
    });

    // 打开 what-if 抽屉
    log("打开 what-if 沙盘");
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
    await sleep(MED);
    try {
      await clickByText(page, "what-if 沙盘");
      await sleep(MED);
      log("应用锁定 + 重算");
      await clickByText(page, "应用锁定 + 重算三档");
      await sleep(LONG);
      await sleep(MED);
    } catch (e) {
      log(`what-if 操作失败: ${e.message}`);
    }
    // 关抽屉
    try {
      await page.keyboard.press("Escape");
      await sleep(SHORT);
    } catch {}

    // ============== 3:00 - 4:15 ==============
    log("=== 3:00-4:15 对话参谋 ===");
    await navTo(page, "对话参谋", "/chat");
    await sleep(SHORT);
    // 新会话
    try {
      await clickByText(page, "+ 新会话");
      await sleep(SHORT);
    } catch {}

    // 第一条
    log("发问 #1：未来 13 周哪几周会紧？");
    const ta = await page.$("textarea");
    if (ta) {
      await ta.click();
      await page.keyboard.type("未来 13 周哪几周会紧？", { delay: 55 });
      await sleep(SHORT);
      await page.keyboard.press("Enter");
      await sleep(20000); // 等 LLM 回应（V4 thinking 通常 10-20s）
    }

    // 第二条
    log("发问 #2：假设北辰电气回款延后 2 周");
    const ta2 = await page.$("textarea");
    if (ta2) {
      await ta2.click();
      await page.keyboard.type("假设北辰电气回款延后 2 周，重算方案", { delay: 50 });
      await sleep(SHORT);
      await page.keyboard.press("Enter");
      await sleep(30000); // 连环 tool 调用通常 20-30s
    }

    // ============== 4:15 - 4:45 ==============
    log("=== 4:15-4:45 MAPE 看板 + 滚动重跑 ===");
    await navTo(page, "MAPE 看板", "/accuracy");
    await sleep(MED);
    try {
      await clickByText(page, "手动触发滚动重跑");
      await sleep(LONG);
    } catch (e) {
      log(`触发滚动失败: ${e.message}`);
    }
    log("展示 MAPE 柱状图 + 偏差校正表");
    await page.evaluate(async () => {
      window.scrollTo({ top: 0, behavior: "smooth" });
      await new Promise((r) => setTimeout(r, 2500));
      window.scrollTo({ top: 600, behavior: "smooth" });
      await new Promise((r) => setTimeout(r, 3500));
      window.scrollTo({ top: 1400, behavior: "smooth" });
      await new Promise((r) => setTimeout(r, 3000));
    });

    // ============== 4:45 - 5:00 ==============
    log("=== 4:45-5:00 收尾 ===");
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
    await sleep(READ);

    const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
    log(`完成 · 总耗时 ${elapsed}s`);
    log("======== Demo 结束 · 现在停止屏幕录制 ========");
    await sleep(3000);
  } catch (e) {
    console.error("Demo 失败:", e);
  } finally {
    if (process.env.DEMO_KEEP_OPEN !== "1") {
      await browser.close();
    } else {
      log("DEMO_KEEP_OPEN=1：保持浏览器打开以便检查状态");
    }
  }
})();

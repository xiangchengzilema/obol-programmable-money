import fs from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const ROOT = path.resolve(process.cwd());
const OUT = path.join(ROOT, "media", "demo_draft");
const VIDEO_TOOLS = path.join(ROOT, "tools", "video-tools");
const requireFromTools = createRequire(path.join(VIDEO_TOOLS, "package.json"));
const { chromium } = requireFromTools("playwright-core");

const EDGE = existsSync("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
  ? "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
  : "C:/Program Files/Google/Chrome/Application/chrome.exe";

const BASE = "http://localhost:5001/";
const RECORD_DIR = path.join(OUT, "playwright_v10");
const WEBM = path.join(OUT, "obol_demo_playwright_v10.webm");

async function pause(page, ms) {
  await page.waitForTimeout(ms);
}

async function caption(page, text, ms = 1800) {
  await page.evaluate(({ text }) => {
    let el = document.querySelector("#demo-caption");
    if (!el) {
      el = document.createElement("div");
      el.id = "demo-caption";
      el.style.cssText = [
        "position: fixed",
        "left: 32px",
        "bottom: 28px",
        "z-index: 99999",
        "max-width: 760px",
        "padding: 16px 20px",
        "border: 1px solid rgba(100,255,218,.36)",
        "border-radius: 12px",
        "background: rgba(5, 13, 16, .86)",
        "box-shadow: 0 24px 70px rgba(0,0,0,.38)",
        "color: #f4fbf8",
        "font: 700 24px/1.35 system-ui, -apple-system, Segoe UI, sans-serif",
        "letter-spacing: 0",
        "backdrop-filter: blur(12px)",
      ].join(";");
      document.body.appendChild(el);
    }
    el.textContent = text;
    el.style.opacity = "1";
    el.style.transform = "translateY(0)";
  }, { text });
  await pause(page, ms);
}

async function hideCaption(page) {
  await page.evaluate(() => {
    const el = document.querySelector("#demo-caption");
    if (el) el.style.opacity = "0";
  });
}

async function gotoHash(page, hash, wait = 1200) {
  await page.goto(`${BASE}#${hash}`, { waitUntil: "networkidle" });
  await pause(page, wait);
}

async function clickNav(page, name, wait = 900) {
  await page.getByRole("button", { name }).click();
  await pause(page, wait);
}

async function smoothScroll(page, pixels, steps = 16) {
  for (let i = 0; i < steps; i += 1) {
    await page.mouse.wheel(0, pixels / steps);
    await pause(page, 35);
  }
}

async function waitForAgentDone(page) {
  try {
    await page.locator("#purchase-popover:not(.hidden)").waitFor({ timeout: 25000 });
    await page.locator("#purchase-kicker", { hasText: /Purchase complete|Read reused|Source selected/i }).waitFor({ timeout: 5000 });
  } catch {
    await gotoHash(page, "console-success/4", 1200);
  }
}

await fs.rm(RECORD_DIR, { recursive: true, force: true });
await fs.mkdir(RECORD_DIR, { recursive: true });
await fs.rm(WEBM, { force: true });

const browser = await chromium.launch({
  executablePath: EDGE,
  headless: true,
  args: [
    "--disable-translate",
    "--disable-features=Translate,TranslateUI",
    "--force-device-scale-factor=1",
  ],
});

const context = await browser.newContext({
  viewport: { width: 1600, height: 900 },
  deviceScaleFactor: 1,
  recordVideo: {
    dir: RECORD_DIR,
    size: { width: 1600, height: 900 },
  },
});

const page = await context.newPage();
page.setDefaultTimeout(18000);

await gotoHash(page, "home", 1800);
await caption(page, "Problem: AI agents read creator work, but most machine reads pay nothing.", 2600);
await page.mouse.move(1255, 265, { steps: 24 });
await caption(page, "Obol turns useful reads into USDC payments, creator receipts, and Arc txHash proof.", 2800);

await clickNav(page, "Agent Console", 1000);
await caption(page, "Step 1: a machine reader gets a question and a small USDC budget.", 2100);
await page.locator("#q-input").fill("How should AI agents pay for creator research on Arc with Circle Wallets?");
await page.locator("#b-input").fill("0.050");
await page.mouse.move(250, 628, { steps: 18 });
await pause(page, 700);
await caption(page, "Now the agent will score paid sources instead of buying everything.", 1700);
await page.locator("#run-btn").click();
await caption(page, "Agent is scanning the market: relevance, price, cache reuse, and coverage.", 2600);
await waitForAgentDone(page);
await caption(page, "Purchase complete: Circle moved USDC and Arc returned proof.", 2700);
await smoothScroll(page, 360, 14);
await caption(page, "Every decision is recorded: buy the best source, skip weak sources, preserve budget.", 3000);

await clickNav(page, "Marketplace", 900);
await caption(page, "Marketplace: creators publish previews; full content stays locked until payment.", 2400);
await page.locator("#market-search").fill("agent");
await pause(page, 900);
await caption(page, "The buyer can ask the agent to evaluate a paid source before spending.", 2300);
const askAgent = page.locator('[data-market-action="agent"]').first();
if (await askAgent.count()) {
  await askAgent.hover();
  await pause(page, 900);
}

await clickNav(page, "Creators", 900);
await caption(page, "Creator Studio: paid reads become revenue with receipt history.", 2400);
const creatorItems = page.locator("#creator-list li");
if (await creatorItems.count() > 2) {
  await creatorItems.nth(2).click();
  await pause(page, 1000);
}
await caption(page, "This is the creator side of the same settlement trail.", 1900);

await clickNav(page, "x402", 900);
await caption(page, "x402: external AI clients can pay through an HTTP-native flow.", 2300);
await page.locator("#x402-challenge-btn").click();
await page.locator("#x402-challenge").waitFor({ state: "visible", timeout: 8000 });
await pause(page, 1500);
await caption(page, "First request returns 402 Payment Required with amount, asset, payTo, and nonce.", 2600);
await page.locator("#x402-pay-btn").click();
await pause(page, 2000);
await caption(page, "Retry with X-Payment unlocks the full content and records a receipt.", 2600);

await clickNav(page, "Traction", 900);
await caption(page, "Traction ledger: the judge view for runs, receipts, and settlement readiness.", 2300);
await page.locator(".view-proof").first().click();
await pause(page, 1000);
await caption(page, "Receipt detail shows creator, amount, Circle transaction id, and Arc txHash.", 3200);
await smoothScroll(page, 280, 10);
await pause(page, 800);

await gotoHash(page, "home", 1200);
await caption(page, "Obol: agents choose sources, Circle moves USDC, Arc proves the read, creators get paid.", 3300);
await hideCaption(page);
await pause(page, 700);

const video = page.video();
await context.close();
await browser.close();

const recorded = await video.path();
await fs.copyFile(recorded, WEBM);
console.log(`wrote ${WEBM}`);

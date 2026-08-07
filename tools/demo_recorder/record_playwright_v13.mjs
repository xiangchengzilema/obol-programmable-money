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
const RECORD_DIR = path.join(OUT, "playwright_v13");
const WEBM = path.join(OUT, "obol_demo_playwright_v13.webm");

async function pause(page, ms) {
  await page.waitForTimeout(ms);
}

async function caption(page, text, ms = 2400) {
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
        "max-width: 820px",
        "padding: 16px 20px",
        "border: 1px solid rgba(100,255,218,.40)",
        "border-radius: 12px",
        "background: rgba(5, 13, 16, .88)",
        "box-shadow: 0 24px 70px rgba(0,0,0,.42)",
        "color: #f4fbf8",
        "font: 700 24px/1.35 system-ui, -apple-system, Segoe UI, sans-serif",
        "backdrop-filter: blur(12px)",
      ].join(";");
      document.body.appendChild(el);
    }
    el.textContent = text;
    el.style.opacity = "1";
  }, { text });
  await pause(page, ms);
}

async function gotoHash(page, hash, wait = 1600) {
  await page.goto(`${BASE}#${hash}`, { waitUntil: "networkidle" });
  await pause(page, wait);
}

async function clickNav(page, name, wait = 1200) {
  await page.getByRole("button", { name }).click();
  await pause(page, wait);
}

async function smoothScroll(page, pixels, steps = 18) {
  for (let i = 0; i < steps; i += 1) {
    await page.mouse.wheel(0, pixels / steps);
    await pause(page, 40);
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
page.setDefaultTimeout(20000);

await gotoHash(page, "home", 2200);
await caption(page, "AI agents consume creator knowledge every day. Most of those reads create no revenue.", 3200);
await page.mouse.move(1280, 270, { steps: 28 });
await caption(page, "Obol converts a useful read into USDC settlement, a creator receipt, and an Arc transaction proof.", 3600);

await clickNav(page, "Agent Console", 1200);
await caption(page, "The buyer is an autonomous research agent with a question, a budget, and a payment policy.", 2600);
await page.locator("#q-input").fill("How should AI agents pay for creator research on Arc with Circle Wallets?");
await page.locator("#b-input").fill("0.050");
await page.mouse.move(225, 508, { steps: 20 });
await caption(page, "It must decide which paid sources are worth purchasing before any USDC moves.", 2400);
await gotoHash(page, "console-pending", 800);
await caption(page, "The agent scores relevance, compares prices, checks cache reuse, and protects the remaining budget.", 4200);
await gotoHash(page, "console-success/4", 1800);
await caption(page, "A single source is selected. Circle submits the payment, and Arc returns the settlement proof.", 4200);
await smoothScroll(page, 360, 18);
await caption(page, "The decision log explains every buy, skip, and reuse decision for auditability.", 3600);

await clickNav(page, "Marketplace", 1200);
await caption(page, "Creators publish paid research with public previews. Full content remains locked until payment.", 4200);
await page.locator("#market-search").fill("agent");
await pause(page, 1400);
const firstAsk = page.locator('[data-market-action="agent"]').first();
if (await firstAsk.count()) {
  await firstAsk.hover();
  await caption(page, "The agent can evaluate a source first, then purchase only when it improves the answer.", 3600);
}

await clickNav(page, "Creators", 1200);
await caption(page, "Creator Studio shows the seller side of the network: revenue, paid reads, and receipt history.", 4200);
const creatorItems = page.locator("#creator-list li");
if (await creatorItems.count() > 2) {
  await creatorItems.nth(2).click();
  await pause(page, 1200);
}
await caption(page, "Each creator has an independent payout trail, so earnings reflect actual paid reads.", 3600);

await clickNav(page, "x402", 1200);
await caption(page, "x402 exposes the same market to external agents through an HTTP-native payment flow.", 4200);
await page.locator("#x402-challenge-btn").click();
await page.locator("#x402-challenge").waitFor({ timeout: 10000 });
await pause(page, 2000);
await caption(page, "The 402 challenge specifies the asset, amount, payee, resource, and nonce required to unlock access.", 4000);
await page.locator("#x402-pay-btn").click();
await pause(page, 2600);
await caption(page, "The client retries with an X-Payment proof; Obol unlocks the content and records the receipt.", 4200);

await clickNav(page, "Traction", 1200);
await caption(page, "The traction ledger gives judges a consolidated view of runs, receipts, settlement status, and paid volume.", 4200);
await page.locator(".view-proof").first().click();
await pause(page, 1400);
await caption(page, "Each receipt exposes the creator, amount, Circle transaction id, and Arc txHash for verification.", 4800);
await smoothScroll(page, 280, 12);
await pause(page, 1200);

await gotoHash(page, "home", 1600);
await caption(page, "Obol makes machine reading accountable: agents choose sources, Circle settles USDC, Arc verifies the transfer, and creators get paid.", 5200);
await page.evaluate(() => document.querySelector("#demo-caption")?.remove());
await pause(page, 900);

const video = page.video();
await context.close();
await browser.close();

const recorded = await video.path();
await fs.copyFile(recorded, WEBM);
console.log(`wrote ${WEBM}`);

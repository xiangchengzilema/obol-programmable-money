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
const RECORD_DIR = path.join(OUT, "playwright_v20_raw_timeline");
const WEBM = path.join(OUT, "obol_demo_playwright_v20_raw_timeline.webm");

const segments = [
  {
    id: "problem",
    duration: 8000,
    caption: "AI agents read creator work. Most machine reads still create no revenue.",
    action: async (page) => {
      await gotoHash(page, "home", 800);
      await page.mouse.move(1230, 320, { steps: 28 });
    },
  },
  {
    id: "thesis",
    duration: 7500,
    caption: "Obol turns useful reads into USDC settlement, creator receipts, and Arc proof.",
    action: async (page) => {
      await page.mouse.move(1380, 675, { steps: 32 });
    },
  },
  {
    id: "agent-buyer",
    duration: 7500,
    caption: "The buyer is an autonomous agent with a question, a budget, and a payment policy.",
    action: async (page) => {
      await clickNav(page, "Agent Console", 700);
      await page.locator("#q-input").fill("Designing x402 endpoints for AI buyers");
      await page.locator("#b-input").fill("0.013");
      await page.mouse.move(250, 505, { steps: 20 });
    },
  },
  {
    id: "before-payment",
    duration: 9500,
    caption: "Before USDC moves, the agent scores relevance, compares prices, and checks cache reuse.",
    action: async (page) => {
      await gotoHash(page, "console-pending", 700);
    },
  },
  {
    id: "settlement",
    duration: 9500,
    caption: "Circle submits the wallet payment; the creator receives USDC; Arc returns proof.",
    action: async (page) => {
      await gotoHash(page, "console-success/4", 900);
      await page.mouse.move(930, 650, { steps: 24 });
    },
  },
  {
    id: "auditability",
    duration: 8000,
    caption: "The decision log explains every buy, skip, and reuse decision.",
    action: async (page) => {
      await smoothScroll(page, 380, 22);
    },
  },
  {
    id: "marketplace",
    duration: 9000,
    caption: "Creators publish paid research with previews. Full content stays locked until payment.",
    action: async (page) => {
      await clickNav(page, "Marketplace", 700);
      await page.locator("#market-search").fill("agent");
      const firstAsk = page.locator('[data-market-action="agent"]').first();
      if (await firstAsk.count()) await firstAsk.hover();
    },
  },
  {
    id: "creator-side",
    duration: 9000,
    caption: "Creator Studio shows paid reads, revenue, receipt history, and payout trails.",
    action: async (page) => {
      await clickNav(page, "Creators", 700);
      const items = page.locator("#creator-list li");
      if (await items.count() > 2) await items.nth(2).click();
    },
  },
  {
    id: "x402",
    duration: 11000,
    caption: "x402 exposes the market to external agents through an HTTP-native payment flow.",
    action: async (page) => {
      await clickNav(page, "x402", 700);
      await page.locator("#x402-challenge-btn").click();
      await page.locator("#x402-challenge").waitFor({ timeout: 10000 });
      await page.waitForTimeout(1800);
      await page.locator("#x402-pay-btn").click();
    },
  },
  {
    id: "traction",
    duration: 12000,
    caption: "Each agent receipt shows creator, amount, Circle transaction id, and Arc txHash.",
    action: async (page) => {
      await clickNav(page, "Traction", 700);
      await page.evaluate(() => {
        const rows = [...document.querySelectorAll("#ledger-list tr[data-ledger-index]")];
        const preferred =
          rows.find((row) => row.textContent.includes("Designing x402 endpoints for AI buyers")) ||
          rows.find((row) => (row.children[1]?.textContent || "").trim().toLowerCase() === "agent") ||
          rows[0];
        preferred?.querySelector(".view-proof")?.click();
      });
    },
  },
  {
    id: "closing",
    duration: 8000,
    caption: "Agents choose sources. Circle settles USDC. Arc verifies the transfer. Creators get paid.",
    action: async (page) => {
      await gotoHash(page, "home", 700);
      await page.waitForTimeout(2600);
      await showEndSlate(page);
    },
  },
];

async function pause(page, ms) {
  await page.waitForTimeout(ms);
}

async function showCaption(page, text) {
  // v20 is a clean screen-recording plate. Remotion owns subtitles and motion.
  void page;
  void text;
}

async function gotoHash(page, hash, wait = 800) {
  await page.goto(`${BASE}#${hash}`, { waitUntil: "networkidle" });
  await page.evaluate(async () => {
    if (typeof window.applyRecordingScene === "function") {
      await window.applyRecordingScene();
    }
  }).catch(() => {});
  await pause(page, wait);
}

async function clickNav(page, name, wait = 700) {
  await page.getByRole("button", { name }).click();
  await pause(page, wait);
}

async function smoothScroll(page, pixels, steps = 18) {
  for (let i = 0; i < steps; i += 1) {
    await page.mouse.wheel(0, pixels / steps);
    await pause(page, 35);
  }
}

async function showEndSlate(page) {
  await page.evaluate(() => {
    document.querySelector("#demo-caption")?.remove();
    const slate = document.createElement("section");
    slate.id = "demo-end-slate";
    slate.innerHTML = `
      <div class="end-mark">O</div>
      <p class="end-kicker">OBOL / ARC TESTNET SETTLEMENT</p>
      <h1>Agents choose sources.<br>Circle settles USDC.<br>Arc verifies the transfer.</h1>
      <div class="end-proof">
        <span>creator receipts</span>
        <span>Circle transaction id</span>
        <span>Arc txHash</span>
      </div>
      <p class="end-line">Pay-per-read settlement for the agent economy.</p>
    `;
    slate.style.cssText = [
      "position: fixed",
      "inset: 0",
      "z-index: 100000",
      "display: grid",
      "place-content: center",
      "gap: 24px",
      "padding: 64px",
      "background: radial-gradient(circle at 50% 38%, rgba(98, 240, 204, .16), transparent 34%), linear-gradient(135deg, #07100f, #0b1417 48%, #050708)",
      "color: #f6fbf8",
      "text-align: center",
      "font-family: system-ui, -apple-system, Segoe UI, sans-serif",
      "letter-spacing: 0",
    ].join(";");
    const style = document.createElement("style");
    style.textContent = `
      #demo-end-slate .end-mark {
        width: 88px; height: 88px; border-radius: 999px; margin: 0 auto;
        display: grid; place-items: center; color: #16140b; font: 900 44px/1 ui-serif, Georgia, serif;
        background: radial-gradient(circle at 30% 25%, #fff4ad, #e6b642 56%, #8a641b);
        box-shadow: 0 0 0 1px rgba(255,255,255,.16), 0 24px 80px rgba(225, 186, 73, .28);
      }
      #demo-end-slate .end-kicker {
        color: #f2ce63; font: 800 14px/1.2 ui-monospace, SFMono-Regular, Menlo, monospace;
        letter-spacing: .12em; text-transform: uppercase; margin: 0;
      }
      #demo-end-slate h1 {
        font-size: 64px; line-height: 1.06; margin: 0; letter-spacing: 0; max-width: 1120px;
      }
      #demo-end-slate .end-proof {
        display: flex; justify-content: center; gap: 16px; flex-wrap: wrap;
      }
      #demo-end-slate .end-proof span {
        border: 1px solid rgba(100,255,218,.28); border-radius: 999px;
        padding: 12px 18px; color: #70f2d2; background: rgba(10, 30, 28, .56);
        font: 800 16px/1.2 ui-monospace, SFMono-Regular, Menlo, monospace;
      }
      #demo-end-slate .end-line {
        color: #b8c7c4; font: 600 22px/1.5 system-ui, sans-serif; margin: 0;
      }
    `;
    document.head.appendChild(style);
    document.body.appendChild(slate);
  });
}

async function runSegment(page, seg) {
  const started = Date.now();
  await showCaption(page, seg.caption);
  await seg.action(page);
  const elapsed = Date.now() - started;
  if (elapsed < seg.duration) {
    await pause(page, seg.duration - elapsed);
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

await gotoHash(page, "home", 1000);
await pause(page, 500);

for (const seg of segments) {
  await runSegment(page, seg);
}

const video = page.video();
await context.close();
await browser.close();

const recorded = await video.path();
await fs.copyFile(recorded, WEBM);
console.log(`wrote ${WEBM}`);

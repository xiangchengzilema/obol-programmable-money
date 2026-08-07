import fs from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { spawn, spawnSync } from "node:child_process";

const ROOT = path.resolve(process.cwd());
const OUT = path.join(ROOT, "media", "demo_draft");
const RECORDER_TOOLS = path.join(ROOT, "tools", "demo_recorder");
const REMOTION_PUBLIC = path.join(ROOT, "tools", "remotion", "public");
const requireFromTools = createRequire(path.join(RECORDER_TOOLS, "package.json"));
const { chromium } = requireFromTools("playwright-core");

const EDGE = existsSync("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
  ? "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
  : "C:/Program Files/Google/Chrome/Application/chrome.exe";

const FFMPEG = process.env.OBOL_FFMPEG_PATH || path.join(
  ROOT,
  "tools",
  "remotion",
  "node_modules",
  "@remotion",
  "compositor-win32-x64-msvc",
  "ffmpeg.exe",
);
const normalizeBase = (value) => `${value.replace(/\/+$/, "")}/`;
const BASE = normalizeBase(
  process.env.OBOL_RECORD_BASE || "https://obol-programmable-money.onrender.com/",
);
const RECORD_DIR = path.join(OUT, "playwright_v23_submit");
const CHECK_DIR = path.join(OUT, "v23_checks");
const WEBM = path.join(OUT, "obol_demo_playwright_v23_submit.webm");
const RAW_MP4 = path.join(OUT, "obol_demo_v23_raw_plate.mp4");
const PUBLIC_RAW_MP4 = path.join(REMOTION_PUBLIC, "obol_demo_v23_raw_plate.mp4");
let localBackend = null;

const segments = [
  {
    id: "01_problem",
    duration: 8000,
    action: async (page) => {
      await gotoScene(page, "home", 900);
      await page.mouse.move(1160, 260, { steps: 30 });
      await shot(page, "01_home_problem");
    },
  },
  {
    id: "02_solution",
    duration: 7500,
    action: async (page) => {
      await page.mouse.move(1280, 566, { steps: 28 });
      await page.evaluate(() => {
        const evidence = document.querySelector("#verified-evidence") || document.querySelector("#live-proof");
        evidence?.scrollIntoView({ block: "center", behavior: "smooth" });
      });
      await page.waitForTimeout(1400);
      await shot(page, "02_live_arc_proof");
    },
  },
  {
    id: "03_agent_buyer",
    duration: 7500,
    action: async (page) => {
      await clickNav(page, "console", 900);
      await page.locator("#q-input").fill("How should an AI agent pay for creator research on Arc with Circle Wallets?");
      await page.locator("#b-input").fill("0.050");
      await page.mouse.move(250, 520, { steps: 20 });
      await shot(page, "03_agent_buyer");
    },
  },
  {
    id: "04_source_selection",
    duration: 9500,
    action: async (page) => {
      await clickId(page, "quick-demo-btn");
      await page.waitForTimeout(1500);
      await shot(page, "04_agent_scoring");
    },
  },
  {
    id: "05_live_settlement",
    duration: 9500,
    action: async (page) => {
      await page.waitForTimeout(1700);
      await page.mouse.move(1160, 590, { steps: 20 });
      await page.evaluate(() => {
        document.querySelector("#run-dashboard")?.scrollIntoView({ block: "center", behavior: "smooth" });
      });
      await page.waitForTimeout(700);
      await shot(page, "05_agent_settlement");
    },
  },
  {
    id: "06_audit_log",
    duration: 8000,
    action: async (page) => {
      await page.evaluate(() => {
        document.querySelector("#decision-section")?.scrollIntoView({ block: "center", behavior: "smooth" });
      });
      await page.waitForTimeout(900);
      await shot(page, "06_decision_log");
    },
  },
  {
    id: "07_marketplace",
    duration: 9000,
    action: async (page) => {
      await clickNav(page, "market", 900);
      await page.locator("#market-search").fill("Arc testnet");
      await page.mouse.move(640, 390, { steps: 24 });
      await page.waitForTimeout(600);
      await shot(page, "07_marketplace");
    },
  },
  {
    id: "08_creator_side",
    duration: 9000,
    action: async (page) => {
      await clickNav(page, "creators", 900);
      const creatorItems = page.locator("#creator-list li");
      if (await creatorItems.count() > 3) {
        await creatorItems.nth(3).click();
      }
      await page.mouse.move(1100, 575, { steps: 24 });
      await page.waitForTimeout(650);
      await shot(page, "08_creators");
    },
  },
  {
    id: "09_x402_access",
    duration: 11000,
    action: async (page) => {
      await clickNav(page, "x402", 900);
      await clickId(page, "x402-challenge-btn");
      await page.waitForTimeout(1100);
      await clickId(page, "x402-pay-btn");
      await page.waitForTimeout(1200);
      await shot(page, "09_x402");
    },
  },
  {
    id: "10_traction_proof",
    duration: 12000,
    action: async (page) => {
      await clickNav(page, "traction", 1000);
      await page.evaluate(() => {
        const rows = [...document.querySelectorAll("#ledger-list tr[data-ledger-index]")];
        const preferred = rows.find((row) => row.textContent.includes("The Arc Letter")) || rows[0];
        preferred?.querySelector(".view-proof")?.click();
      });
      await page.waitForTimeout(900);
      await page.mouse.move(1270, 520, { steps: 28 });
      await shot(page, "10_traction");
    },
  },
  {
    id: "11_closing",
    duration: 8000,
    action: async (page) => {
      await gotoScene(page, "home", 900);
      await page.waitForTimeout(2200);
      await showEndSlate(page);
      await shot(page, "11_end_slate");
    },
  },
];

async function ensureBackend() {
  try {
    const res = await fetch(`${BASE}api/health`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const body = await res.json();
    if (body.status !== "ok") throw new Error(JSON.stringify(body));
  } catch (error) {
    throw new Error(`Backend is not reachable at ${BASE}: ${error.message}`);
  }
}

async function startLocalBackend() {
  const target = new URL(BASE);
  if (!["127.0.0.1", "localhost"].includes(target.hostname)) {
    throw new Error(`OBOL_START_LOCAL=1 requires a localhost URL, received ${BASE}`);
  }
  const port = target.port || "5001";
  const dbPath = process.env.OBOL_RECORD_DB || path.join(OUT, "obol_video_v23.db");
  localBackend = spawn(process.env.OBOL_PYTHON || "python", ["app.py"], {
    cwd: path.join(ROOT, "backend"),
    windowsHide: true,
    stdio: "ignore",
    env: {
      ...process.env,
      PORT: port,
      OBOL_PUBLIC_DEMO: "1",
      OBOL_FORCE_MOCK: "1",
      OBOL_AUTO_SEED: "1",
      OBOL_DB_PATH: dbPath,
    },
  });
  localBackend.once("exit", (code) => {
    if (code && code !== 0) {
      console.error(`local backend exited early with code ${code}`);
    }
  });
  for (let attempt = 0; attempt < 60; attempt += 1) {
    try {
      await ensureBackend();
      console.log(`started local final-commit demo backend at ${BASE}`);
      return;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
  }
  throw new Error(`Local backend did not become ready at ${BASE}`);
}

async function pause(page, ms) {
  await page.waitForTimeout(ms);
}

async function installRecordingMode(page) {
  await page.addStyleTag({
    content: `
      html, body {
        width: 100% !important;
        overflow-x: hidden !important;
        scroll-behavior: smooth !important;
      }
      body {
        --recording-panel: rgba(13, 29, 43, .92);
        --recording-panel-soft: rgba(19, 43, 62, .72);
        background: #07131f !important;
      }
      body::after {
        content: "";
        position: fixed;
        inset: 0;
        pointer-events: none;
        z-index: 99998;
        background:
          linear-gradient(90deg, rgba(255,255,255,.035), transparent 8%, transparent 92%, rgba(255,255,255,.025)),
          radial-gradient(circle at 84% 14%, rgba(74, 190, 255, .10), transparent 30%),
          radial-gradient(circle at 12% 18%, rgba(255, 74, 213, .10), transparent 28%);
        mix-blend-mode: screen;
      }
      .cursor-glow,
      .motion-surface::before {
        opacity: .22 !important;
        animation: none !important;
      }
      .topbar {
        width: min(1440px, calc(100vw - 64px)) !important;
        left: 50% !important;
        right: auto !important;
        transform: translateX(-50%) !important;
        display: grid !important;
        grid-template-columns: 250px minmax(600px, 1fr) 300px !important;
        gap: 16px !important;
        align-items: center !important;
        backdrop-filter: blur(22px) saturate(1.25) !important;
      }
      .nav {
        display: grid !important;
        grid-template-columns: repeat(6, minmax(88px, 1fr)) !important;
        gap: 8px !important;
      }
      .navbtn {
        min-width: 0 !important;
        height: 44px !important;
        padding: 0 10px !important;
        white-space: nowrap !important;
      }
      .system-state {
        display: grid !important;
        grid-template-columns: minmax(180px, 1fr) 104px !important;
        gap: 10px !important;
        align-items: center !important;
      }
      #mode-pill {
        width: 100% !important;
        min-width: 0 !important;
        justify-content: center !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        white-space: nowrap !important;
      }
      .topbar-cta {
        height: 44px !important;
        min-width: 104px !important;
        padding: 0 14px !important;
        white-space: nowrap !important;
      }
      main {
        width: min(1440px, calc(100vw - 64px)) !important;
        margin-inline: auto !important;
      }
      .hero-grid {
        grid-template-columns: minmax(0, .98fr) minmax(480px, .72fr) !important;
        gap: 40px !important;
        min-height: 750px !important;
      }
      .hero-copy h1 {
        font-size: clamp(64px, 7.8vw, 104px) !important;
        line-height: .96 !important;
        max-width: 780px !important;
      }
      .proof-card {
        max-height: 680px !important;
        min-height: 0 !important;
        overflow: hidden !important;
      }
      .terminal-feed {
        max-height: 116px !important;
        overflow: hidden !important;
      }
      .console-layout {
        grid-template-columns: 360px minmax(0, 1fr) !important;
        gap: 24px !important;
      }
      .result-stage {
        min-height: 560px !important;
        overflow: hidden !important;
      }
      .run-dashboard {
        display: grid !important;
        grid-template-columns: repeat(12, minmax(0, 1fr)) !important;
        gap: 16px !important;
      }
      .chain-lens,
      .agent-market-scan,
      .run-steps {
        grid-column: 1 / -1 !important;
      }
      .chain-lens {
        display: grid !important;
        grid-template-columns: repeat(4, minmax(0, 1fr)) !important;
        gap: 16px !important;
      }
      .chain-lens article {
        min-height: 140px !important;
        padding: 18px !important;
      }
      .chain-lens strong,
      .scan-lane strong,
      .result-proof-grid strong,
      .article h3 {
        line-height: 1.16 !important;
        letter-spacing: 0 !important;
        overflow-wrap: normal !important;
      }
      .scan-lane {
        grid-template-columns: repeat(4, minmax(0, 1fr)) !important;
        gap: 14px !important;
      }
      .scan-lane article {
        min-height: 148px !important;
      }
      .plan-card {
        grid-column: 1 / 7 !important;
        min-height: 122px !important;
      }
      .coverage-card {
        grid-column: 7 / -1 !important;
        min-height: 122px !important;
      }
      .metric-row {
        grid-column: 1 / 7 !important;
        display: grid !important;
        grid-template-columns: repeat(4, minmax(0, 1fr)) !important;
        gap: 12px !important;
      }
      .metric-row article {
        min-width: 0 !important;
        min-height: 112px !important;
        padding: 16px !important;
      }
      .metric-row article strong,
      .metric-row article .num {
        font-size: 26px !important;
        white-space: nowrap !important;
        overflow: visible !important;
      }
      .result-proof-grid {
        grid-column: 7 / -1 !important;
        grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
        gap: 12px !important;
      }
      .detail-grid {
        gap: 20px !important;
      }
      .table-wrap,
      .ledger-table,
      .decisions {
        overflow: hidden !important;
      }
      .market-grid {
        grid-template-columns: repeat(4, minmax(0, 1fr)) !important;
        gap: 18px !important;
      }
      .article {
        min-height: 258px !important;
        padding: 18px !important;
        display: flex !important;
        flex-direction: column !important;
      }
      .article .preview {
        max-height: 48px !important;
        overflow: hidden !important;
      }
      .article-actions {
        margin-top: auto !important;
      }
      .creator-studio {
        display: grid !important;
        grid-template-columns: 330px minmax(0, 1fr) !important;
        gap: 22px !important;
      }
      .create-form {
        max-height: 640px !important;
        overflow: hidden !important;
      }
      .creators-layout {
        grid-template-columns: 260px minmax(0, 1fr) !important;
        gap: 18px !important;
      }
      .creator-payments {
        max-height: 370px !important;
        overflow: hidden !important;
      }
      .x402-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
        gap: 24px !important;
      }
      .codebox {
        max-height: 330px !important;
        overflow: hidden !important;
        font-size: 13px !important;
        line-height: 1.55 !important;
      }
      .traction-grid,
      #ledger-list {
        overflow: hidden !important;
      }
      .receipt-drawer {
        width: 470px !important;
        max-width: 470px !important;
      }
      *::-webkit-scrollbar {
        width: 8px !important;
        height: 8px !important;
      }
      *::-webkit-scrollbar-track {
        background: rgba(5, 16, 26, .72) !important;
      }
      *::-webkit-scrollbar-thumb {
        background: linear-gradient(180deg, rgba(103, 242, 214, .8), rgba(82, 164, 255, .74)) !important;
        border-radius: 999px !important;
      }
      select, input, textarea {
        background: rgba(3, 13, 24, .88) !important;
        color: #f8fbff !important;
      }
    `,
  });
  await page.evaluate(() => {
    document.body.classList.add("recording-mode");
  });
}

async function gotoScene(page, scene, wait = 700) {
  await page.goto(`${BASE}#${scene}`, { waitUntil: "networkidle" });
  await installRecordingMode(page);
  await page.evaluate(async () => {
    if (typeof window.applyRecordingScene === "function") {
      await window.applyRecordingScene();
    }
  }).catch(() => {});
  await pause(page, wait);
}

async function clickNav(page, viewName, wait = 700) {
  await page.evaluate((targetView) => {
    document.querySelector(`.nav button[data-view="${targetView}"]`)?.click();
  }, viewName);
  await installRecordingMode(page);
  await pause(page, wait);
}

async function clickId(page, id) {
  await page.evaluate((targetId) => document.getElementById(targetId)?.click(), id);
}

async function shot(page, name) {
  await fs.mkdir(CHECK_DIR, { recursive: true });
  await page.screenshot({ path: path.join(CHECK_DIR, `${name}.jpg`), quality: 86, type: "jpeg" });
}

async function showEndSlate(page) {
  await page.evaluate(() => {
    document.querySelector("#demo-end-slate")?.remove();
    const slate = document.createElement("section");
    slate.id = "demo-end-slate";
    slate.innerHTML = `
      <div class="end-grid">
        <div class="end-mark">O</div>
        <p>OBOL / ARC TESTNET SETTLEMENT</p>
        <h1>Agents choose sources.<br>Circle settles USDC.<br>Arc verifies the transfer.</h1>
        <div class="end-proof">
          <span>Creator receipts</span>
          <span>Circle transaction id</span>
          <span>Arc txHash</span>
        </div>
      </div>
    `;
    const style = document.createElement("style");
    style.textContent = `
      #demo-end-slate {
        position: fixed;
        inset: 0;
        z-index: 100000;
        display: grid;
        place-items: center;
        padding: 64px;
        background:
          radial-gradient(circle at 50% 36%, rgba(92, 239, 208, .20), transparent 30%),
          radial-gradient(circle at 8% 18%, rgba(255, 63, 214, .16), transparent 34%),
          linear-gradient(135deg, #07111e, #0b1c1d 48%, #05080d);
        color: #f6fbf8;
        text-align: center;
      }
      #demo-end-slate .end-grid {
        display: grid;
        gap: 20px;
        justify-items: center;
      }
      #demo-end-slate .end-mark {
        width: 88px;
        height: 88px;
        border-radius: 24px;
        display: grid;
        place-items: center;
        color: #17150b;
        font: 900 44px/1 ui-serif, Georgia, serif;
        background: radial-gradient(circle at 30% 24%, #fff4ad, #e6b642 56%, #8a641b);
        box-shadow: 0 0 0 1px rgba(255,255,255,.16), 0 24px 80px rgba(225, 186, 73, .26);
      }
      #demo-end-slate p {
        margin: 0;
        color: #f2ce63;
        font: 900 14px/1.2 ui-monospace, SFMono-Regular, Menlo, monospace;
        letter-spacing: .13em;
      }
      #demo-end-slate h1 {
        margin: 0;
        max-width: 1120px;
        color: white;
        font: 950 64px/1.05 system-ui, -apple-system, Segoe UI, sans-serif;
        letter-spacing: 0;
      }
      #demo-end-slate .end-proof {
        display: flex;
        flex-wrap: wrap;
        gap: 16px;
        justify-content: center;
      }
      #demo-end-slate .end-proof span {
        border: 1px solid rgba(100,255,218,.30);
        border-radius: 999px;
        padding: 12px 18px;
        color: #70f2d2;
        background: rgba(10, 30, 38, .64);
        font: 800 16px/1.2 ui-monospace, SFMono-Regular, Menlo, monospace;
      }
    `;
    document.head.appendChild(style);
    document.body.appendChild(slate);
  });
}

async function runSegment(page, seg) {
  const started = Date.now();
  await seg.action(page);
  const elapsed = Date.now() - started;
  console.log(`${seg.id} action=${elapsed}ms hold=${Math.max(0, seg.duration - elapsed)}ms`);
  if (elapsed < seg.duration) {
    await pause(page, seg.duration - elapsed);
  }
}

function runFfmpeg(args) {
  const result = spawnSync(FFMPEG, args, { cwd: ROOT, stdio: "inherit" });
  if (result.status !== 0) {
    throw new Error(`ffmpeg failed with exit ${result.status}`);
  }
}

async function main() {
if (process.env.OBOL_START_LOCAL === "1") {
  await startLocalBackend();
} else {
  await ensureBackend();
}
if (!existsSync(FFMPEG)) {
  throw new Error(`ffmpeg is not available at ${FFMPEG}. Run npm ci in tools/remotion first.`);
}
await fs.rm(RECORD_DIR, { recursive: true, force: true });
await fs.rm(CHECK_DIR, { recursive: true, force: true });
await fs.rm(WEBM, { force: true });
await fs.rm(RAW_MP4, { force: true });
await fs.mkdir(RECORD_DIR, { recursive: true });
await fs.mkdir(OUT, { recursive: true });

const browser = await chromium.launch({
  executablePath: EDGE,
  headless: true,
  args: [
    "--disable-translate",
    "--disable-features=Translate,TranslateUI",
    "--force-device-scale-factor=1",
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
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

for (const seg of segments) {
  console.log(`recording ${seg.id}`);
  await runSegment(page, seg);
}

const video = page.video();
await context.close();
await browser.close();

const recorded = await video.path();
await fs.copyFile(recorded, WEBM);
console.log(`wrote ${WEBM}`);

runFfmpeg([
  "-y",
  "-ss", "0.12",
  "-i", WEBM,
  "-r", "30",
  "-pix_fmt", "yuv420p",
  "-t", "99",
  "-an",
  "-c:v", "libx264",
  "-preset", "medium",
  "-crf", "19",
  RAW_MP4,
]);

await fs.copyFile(RAW_MP4, PUBLIC_RAW_MP4);
console.log(`wrote ${RAW_MP4}`);
console.log(`copied ${PUBLIC_RAW_MP4}`);
}

try {
  await main();
} finally {
  localBackend?.kill();
}

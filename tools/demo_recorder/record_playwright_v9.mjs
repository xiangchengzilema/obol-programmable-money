import fs from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { createRequire } from "node:module";

const ROOT = path.resolve(process.cwd());
const OUT = path.join(ROOT, "media", "demo_draft");
const VIDEO_TOOLS = path.join(ROOT, "tools", "video-tools");
const requireFromTools = createRequire(path.join(VIDEO_TOOLS, "package.json"));
const { chromium } = requireFromTools("playwright-core");

const EDGE = existsSync("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
  ? "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
  : "C:/Program Files/Google/Chrome/Application/chrome.exe";
const FFMPEG = path.join(VIDEO_TOOLS, "node_modules", "ffmpeg-static", "ffmpeg.exe");
const RUN_ID = process.argv[2] || "4";
const BASE = "http://localhost:5001/";
const RECORD_DIR = path.join(OUT, "playwright_v9");
const WEBM = path.join(OUT, "obol_demo_playwright_v9.webm");
const MP4 = path.join(OUT, "obol_demo_playwright_v9.mp4");

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function run(cmd, args, cwd = ROOT) {
  return new Promise((resolve, reject) => {
    const p = spawn(cmd, args, { cwd, stdio: "inherit" });
    p.on("exit", (code) => code === 0 ? resolve() : reject(new Error(`${cmd} exited ${code}`)));
  });
}

async function gotoScene(page, scene, hold = 1800) {
  await page.goto(`${BASE}#${scene}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(hold);
}

async function clickNav(page, label, hold = 1500) {
  await page.getByRole("button", { name: label }).click();
  await page.waitForTimeout(hold);
}

async function smallScroll(page, distance = 260, steps = 12) {
  for (let i = 0; i < steps; i += 1) {
    await page.mouse.wheel(0, distance / steps);
    await page.waitForTimeout(28);
  }
}

await fs.rm(RECORD_DIR, { recursive: true, force: true });
await fs.mkdir(RECORD_DIR, { recursive: true });
await fs.rm(WEBM, { force: true });
await fs.rm(MP4, { force: true });

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
page.setDefaultTimeout(15000);

await gotoScene(page, "home", 2500);
await page.mouse.move(185, 680, { steps: 18 });
await page.waitForTimeout(900);

await clickNav(page, "Agent Console", 1200);
await gotoScene(page, "console-setup", 1600);
await page.mouse.move(1295, 226, { steps: 16 });
await page.waitForTimeout(500);
await gotoScene(page, "console-pending", 3400);
await gotoScene(page, `console-success/${RUN_ID}`, 3600);
await smallScroll(page, 340, 18);
await page.waitForTimeout(1200);
await gotoScene(page, `decision-log/${RUN_ID}`, 2500);

await clickNav(page, "Marketplace", 900);
await gotoScene(page, "market", 2600);
await smallScroll(page, 420, 16);
await page.waitForTimeout(800);

await clickNav(page, "Creators", 900);
await gotoScene(page, "creators", 2600);
await page.mouse.move(735, 254, { steps: 10 });
await page.waitForTimeout(800);

await clickNav(page, "x402", 900);
await gotoScene(page, "x402", 2600);
await page.mouse.move(1200, 472, { steps: 10 });
await page.waitForTimeout(900);

await clickNav(page, "Traction", 900);
await gotoScene(page, "traction", 3200);
await smallScroll(page, 300, 12);
await page.waitForTimeout(900);

await gotoScene(page, "home", 2200);

const video = page.video();
await context.close();
await browser.close();

const recorded = await video.path();
await fs.copyFile(recorded, WEBM);

if (!existsSync(FFMPEG)) {
  console.log(`wrote ${WEBM}`);
  console.log("ffmpeg-static not found; leaving webm only");
  process.exit(0);
}

await run(FFMPEG, [
  "-y",
  "-i", WEBM,
  "-vf", "fps=30,format=yuv420p",
  "-c:v", "libx264",
  "-preset", "veryfast",
  "-crf", "20",
  "-movflags", "+faststart",
  MP4,
]);

console.log(`wrote ${MP4}`);

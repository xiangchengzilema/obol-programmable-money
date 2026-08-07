import fs from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const OUT = path.join(ROOT, "media", "demo_draft");
const SHOTS = path.join(OUT, "shots_v5");
const FFMPEG = path.join(ROOT, "tools", "video-tools", "node_modules", "ffmpeg-static", "ffmpeg.exe");
const CHROME = existsSync("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
  ? "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
  : "C:/Program Files/Google/Chrome/Application/chrome.exe";
const RUN_ID = process.argv[2] || "4";
const BASE = "http://localhost:5001/";
const SKIP_CAPTURE = process.env.OBOL_SKIP_CAPTURE === "1";

const scenes = [
  ["01_home", "home", 10, "AI agents read creator work. Obol makes each useful read paid."],
  ["02_proof", "proof", 8, "The first screen shows live settlement proof, not a marketing claim."],
  ["03_console_setup", "console-setup", 8, "The buyer is a machine reader with a budget."],
  ["04_console_pending", "console-pending", 8, "The agent scores sources, selects one, and submits Circle settlement."],
  ["05_console_success", `console-success&run=${RUN_ID}`, 9, "Purchase complete: creator paid, source unlocked, Arc proof returned."],
  ["06_decision_log", `decision-log&run=${RUN_ID}`, 9, "Every payment has a reason: buy, skip, or reuse."],
  ["07_marketplace", "market", 8, "Creators publish previews; full content stays locked until payment."],
  ["08_creators", "creators", 8, "Creators see paid reads as revenue, with receipt history."],
  ["09_x402", "x402", 8, "x402 gives external AI clients a machine-facing payment path."],
  ["10_traction", "traction", 10, "The ledger records creator, amount, Circle id, and Arc txHash."],
  ["11_close", "home", 10, "AI agents choose sources. Circle moves USDC. Arc verifies the transfer."],
];

function run(cmd, args, cwd = ROOT) {
  return new Promise((resolve, reject) => {
    const p = spawn(cmd, args, { cwd, stdio: "inherit" });
    p.on("exit", (code) => code === 0 ? resolve() : reject(new Error(`${cmd} exited ${code}`)));
  });
}

function srtTime(seconds) {
  const ms = Math.round(seconds * 1000);
  const h = Math.floor(ms / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  const s = Math.floor((ms % 60000) / 1000);
  const milli = ms % 1000;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")},${String(milli).padStart(3, "0")}`;
}

if (!SKIP_CAPTURE) {
  await fs.rm(SHOTS, { recursive: true, force: true });
  await fs.mkdir(SHOTS, { recursive: true });
}

let cursor = 0;
const concat = [];
const captions = [];

for (let i = 0; i < scenes.length; i += 1) {
  const [id, scene, duration, caption] = scenes[i];
  const file = path.join(SHOTS, `${id}.jpg`);
  const profile = path.join(OUT, "chrome-shot-profiles", id);
  await fs.mkdir(profile, { recursive: true });
  const url = `${BASE}?scene=${scene}&shot=${id}&v=20260624-31`;
  if (!SKIP_CAPTURE) {
    console.log(`shot ${id}: ${url}`);
    await run(CHROME, [
      "--headless=new",
      "--disable-gpu",
      "--disable-software-rasterizer",
      "--disable-gpu-compositing",
      "--disable-accelerated-2d-canvas",
      "--disable-accelerated-video-decode",
      "--disable-webgl",
      "--use-gl=disabled",
      "--single-process",
      "--no-sandbox",
      "--disable-features=UseSkiaRenderer,DawnGraphite,CanvasOopRasterization",
      "--disable-dev-shm-usage",
      "--hide-scrollbars",
      "--no-first-run",
      "--no-default-browser-check",
      `--user-data-dir=${profile}`,
      "--window-size=1600,900",
      "--force-device-scale-factor=1",
      "--virtual-time-budget=5500",
      `--screenshot=${file}`,
      url,
    ]);
  }
  concat.push(`file '${file.replaceAll("\\", "/")}'`);
  concat.push(`duration ${duration.toFixed(3)}`);
  captions.push(`${i + 1}\n${srtTime(cursor)} --> ${srtTime(cursor + duration)}\n${caption}\n`);
  cursor += duration;
}
concat.push(`file '${path.join(SHOTS, `${scenes.at(-1)[0]}.jpg`).replaceAll("\\", "/")}'`);

await fs.writeFile(path.join(OUT, "slides_static_v5.txt"), concat.join("\n") + "\n", "utf8");
await fs.writeFile(path.join(OUT, "captions_static_v5.srt"), captions.join("\n"), "utf8");

const vf = "scale=1600:900,subtitles=captions_static_v5.srt:force_style='FontName=Arial,FontSize=28,PrimaryColour=&H00FFFFFF,OutlineColour=&H00101010,BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=42'";
await run(FFMPEG, [
  "-y",
  "-f", "concat",
  "-safe", "0",
  "-i", "slides_static_v5.txt",
  "-vf", vf,
  "-c:v", "libx264",
  "-pix_fmt", "yuv420p",
  "-r", "30",
  "obol_demo_draft_v5.mp4",
], OUT);

console.log(`wrote ${path.join(OUT, "obol_demo_draft_v5.mp4")} (${cursor.toFixed(1)}s)`);

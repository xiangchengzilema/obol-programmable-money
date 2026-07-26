import fs from "node:fs/promises";
import { existsSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const OUT = path.join(ROOT, "media", "demo_draft");
const FRAMES = path.join(OUT, "frames_v5");
const SEGMENTS = JSON.parse(await fs.readFile(path.join(OUT, "segments_v5.json"), "utf8"));
const FPS = 4;
const WIDTH = 1600;
const HEIGHT = 900;
const PORT = 9400 + Math.floor(Math.random() * 400);
const CHROME = existsSync("C:/Program Files/Google/Chrome/Application/chrome.exe")
  ? "C:/Program Files/Google/Chrome/Application/chrome.exe"
  : "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const FFMPEG = path.join(ROOT, "tools", "video-tools", "node_modules", "ffmpeg-static", "ffmpeg.exe");

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitFor(fn, timeoutMs = 30000, intervalMs = 250) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const result = await fn();
    if (result) return result;
    await wait(intervalMs);
  }
  return null;
}

function wavDuration(file) {
  if (!existsSync(file)) return 0;
  const stat = statSync(file);
  if (!stat.size) return 0;
  const buf = Buffer.from(requireFs(file));
  if (buf.toString("ascii", 0, 4) !== "RIFF") return 6;
  const sampleRate = buf.readUInt32LE(24);
  const bitsPerSample = buf.readUInt16LE(34);
  const channels = buf.readUInt16LE(22);
  let offset = 12;
  while (offset + 8 < buf.length) {
    const id = buf.toString("ascii", offset, offset + 4);
    const size = buf.readUInt32LE(offset + 4);
    if (id === "data") {
      return size / (sampleRate * channels * (bitsPerSample / 8));
    }
    offset += 8 + size;
  }
  return 6;
}

function requireFs(file) {
  return readFileSync(file);
}

class CDP {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl);
    this.nextId = 1;
    this.pending = new Map();
    this.events = new Map();
    this.opened = new Promise((resolve, reject) => {
      this.ws.addEventListener("open", resolve, { once: true });
      this.ws.addEventListener("error", reject, { once: true });
    });
    this.ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result || {});
      } else if (msg.method) {
        const listeners = this.events.get(msg.method) || [];
        for (const listener of listeners) listener(msg.params || {});
      }
    };
    this.ws.addEventListener("close", () => {
      for (const { reject } of this.pending.values()) reject(new Error("CDP WebSocket closed"));
      this.pending.clear();
    });
  }
  async open() {
    const ok = await Promise.race([
      this.opened.then(() => true),
      waitFor(() => this.ws.readyState === WebSocket.OPEN, 5000, 50),
    ]);
    if (!ok) throw new Error(`WebSocket did not open, state=${this.ws.readyState}`);
  }
  send(method, params = {}) {
    const id = this.nextId++;
    if (this.ws.readyState !== WebSocket.OPEN) {
      return Promise.reject(new Error(`CDP WebSocket not open, state=${this.ws.readyState}`));
    }
    this.ws.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => this.pending.set(id, { resolve, reject }));
  }
  once(method, timeoutMs = 10000) {
    return new Promise((resolve) => {
      const timer = setTimeout(() => resolve(null), timeoutMs);
      const listener = (params) => {
        clearTimeout(timer);
        this.events.set(method, (this.events.get(method) || []).filter((x) => x !== listener));
        resolve(params);
      };
      this.events.set(method, [...(this.events.get(method) || []), listener]);
    });
  }
  close() {
    try { this.ws.close(); } catch {}
  }
}

async function launchChrome() {
  console.log("launching chrome", CHROME);
  const userData = path.join(OUT, "chrome-profile-v5");
  await fs.mkdir(userData, { recursive: true });
  const chrome = spawn(CHROME, [
    "--headless=new",
    `--remote-debugging-port=${PORT}`,
    "--remote-allow-origins=*",
    `--user-data-dir=${userData}`,
    `--window-size=${WIDTH},${HEIGHT}`,
    "--force-device-scale-factor=1",
    "--disable-gpu",
    "--no-first-run",
    "--no-default-browser-check",
    "about:blank",
  ], { stdio: "ignore" });

  const version = await waitFor(async () => {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/json/version`);
      return await r.json();
    } catch {
      return null;
    }
  }, 12000, 250);
  if (!version) throw new Error("Chrome remote debugging did not start");
  return { chrome, version };
}

async function newPage() {
  console.log("opening CDP page");
  const r = await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: "PUT" });
  const target = await r.json();
  console.log("target", target.id, target.type, target.webSocketDebuggerUrl ? "ws-ok" : "no-ws");
  const cdp = new CDP(target.webSocketDebuggerUrl);
  console.log("before cdp.open");
  await cdp.open();
  console.log("after cdp.open");
  console.log("Page.enable");
  await cdp.send("Page.enable");
  console.log("Runtime.enable");
  await cdp.send("Runtime.enable");
  console.log("metrics");
  await cdp.send("Emulation.setDeviceMetricsOverride", {
    width: WIDTH,
    height: HEIGHT,
    deviceScaleFactor: 1,
    mobile: false,
  });
  console.log("navigate");
  await cdp.send("Page.navigate", { url: "http://localhost:5001/?record=v5" });
  await cdp.once("Page.loadEventFired", 15000);
  await wait(900);
  return cdp;
}

async function evalJs(cdp, expression, awaitPromise = true) {
  const result = await cdp.send("Runtime.evaluate", {
    expression,
    awaitPromise,
    returnByValue: true,
  });
  if (result.exceptionDetails) {
    throw new Error(JSON.stringify(result.exceptionDetails));
  }
  return result.result?.value;
}

let frame = 0;
const timings = [];

async function captureFrame(cdp) {
  const shot = await cdp.send("Page.captureScreenshot", {
    format: "jpeg",
    quality: 88,
    fromSurface: true,
  });
  const file = path.join(FRAMES, `frame_${String(frame).padStart(5, "0")}.jpg`);
  await fs.writeFile(file, Buffer.from(shot.data, "base64"));
  frame += 1;
}

async function captureSegment(cdp, segment, duration) {
  console.log(`capture ${segment.id} ${duration.toFixed(1)}s`);
  const startFrame = frame;
  const start = frame / FPS;
  const count = Math.max(8, Math.ceil(duration * FPS));
  for (let i = 0; i < count; i += 1) {
    await captureFrame(cdp);
    await wait(1000 / FPS);
  }
  timings.push({
    id: segment.id,
    caption: segment.caption,
    start,
    end: frame / FPS,
    startFrame,
    endFrame: frame - 1,
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

async function clickView(cdp, view) {
  await evalJs(cdp, `document.querySelector('[data-view="${view}"]').click(); true;`);
  await wait(800);
}

async function buildVideo() {
  const captions = timings.map((t, i) =>
    `${i + 1}\n${srtTime(t.start)} --> ${srtTime(t.end)}\n${t.caption}\n`
  ).join("\n");
  await fs.writeFile(path.join(OUT, "captions_v5.srt"), captions, "utf8");
  await fs.writeFile(path.join(OUT, "scene_timings_v5.json"), JSON.stringify(timings, null, 2), "utf8");

  const vf = "subtitles=captions_v5.srt:force_style='FontName=Arial,FontSize=28,PrimaryColour=&H00FFFFFF,OutlineColour=&H00101010,BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=42'";
  const audioReady = SEGMENTS.every((s) => {
    const wav = path.join(OUT, `${s.id}.wav`);
    return existsSync(wav) && statSync(wav).size > 1024;
  });

  if (audioReady) {
    const audioConcat = SEGMENTS.map((s) => `file '${s.id}.wav'`).join("\n") + "\n";
    await fs.writeFile(path.join(OUT, "audio_concat_v5.txt"), audioConcat, "utf8");
    await run(FFMPEG, [
      "-y", "-f", "concat", "-safe", "0", "-i", "audio_concat_v5.txt",
      "-c", "copy", "voiceover_v5.wav",
    ], OUT);
  }

  const args = [
    "-y",
    "-framerate", String(FPS),
    "-i", "frames_v5/frame_%05d.jpg",
    "-vf", vf,
    "-c:v", "libx264",
    "-pix_fmt", "yuv420p",
    "-r", "30",
  ];
  if (audioReady) {
    args.splice(5, 0, "-i", "voiceover_v5.wav");
    args.push("-c:a", "aac", "-shortest");
  }
  args.push("obol_demo_draft_v5.mp4");
  await run(FFMPEG, args, OUT);
}

function run(cmd, args, cwd) {
  return new Promise((resolve, reject) => {
    const p = spawn(cmd, args, { cwd, stdio: "inherit" });
    p.on("exit", (code) => code === 0 ? resolve() : reject(new Error(`${cmd} exited ${code}`)));
  });
}

async function main() {
  console.log("record_demo_v5 start");
  await fs.rm(FRAMES, { recursive: true, force: true });
  await fs.mkdir(FRAMES, { recursive: true });
  const durations = Object.fromEntries(SEGMENTS.map((s) => {
    const wav = path.join(OUT, `${s.id}.wav`);
    const spoken = wavDuration(wav);
    const fallback = Math.min(13, Math.max(5, s.voice.split(/\s+/).length * 0.36 + 1.2));
    return [s.id, (spoken > 0 ? spoken : fallback) + 0.2];
  }));

  const { chrome } = await launchChrome();
  let cdp = null;
  try {
    cdp = await newPage();
    console.log("page ready");
    await captureSegment(cdp, SEGMENTS[0], durations[SEGMENTS[0].id]);
    await evalJs(cdp, `document.querySelector('#live-proof')?.scrollIntoView({block:'center'}); true;`);
    await wait(700);
    await captureSegment(cdp, SEGMENTS[1], durations[SEGMENTS[1].id]);

    await clickView(cdp, "console");
    await evalJs(cdp, `
      window.scrollTo({top: 0});
      document.querySelector('#q-input').value = 'Designing x402 endpoints for AI buyers';
      document.querySelector('#b-input').value = '0.013';
      true;
    `);
    await captureSegment(cdp, SEGMENTS[2], durations[SEGMENTS[2].id]);
    await evalJs(cdp, `document.querySelector('#run-btn').click(); true;`);
    await captureSegment(cdp, SEGMENTS[3], durations[SEGMENTS[3].id]);

    const final = await waitFor(async () => {
      return evalJs(cdp, `(() => {
        const text = document.querySelector('#purchase-kicker')?.textContent?.trim() || '';
        return /Purchase complete|Read reused|Unlock failed|Error/.test(text) ? text : '';
      })()`);
    }, 85000, 600);
    if (!final || /failed|error/i.test(final)) {
      throw new Error(`Agent run did not reach a clean final state: ${final || "timeout"}`);
    }
    await captureSegment(cdp, SEGMENTS[4], durations[SEGMENTS[4].id]);
    await evalJs(cdp, `document.querySelector('#decision-section')?.scrollIntoView({block:'start'}); true;`);
    await wait(700);
    await captureSegment(cdp, SEGMENTS[5], durations[SEGMENTS[5].id]);

    await clickView(cdp, "market");
    await captureSegment(cdp, SEGMENTS[6], durations[SEGMENTS[6].id]);
    await clickView(cdp, "x402");
    await captureSegment(cdp, SEGMENTS[7], durations[SEGMENTS[7].id]);
    await clickView(cdp, "traction");
    await wait(1000);
    await evalJs(cdp, `document.querySelector('tr[data-ledger-index="0"]')?.click(); true;`);
    await wait(600);
    await captureSegment(cdp, SEGMENTS[8], durations[SEGMENTS[8].id]);
    await clickView(cdp, "creators");
    await captureSegment(cdp, SEGMENTS[9], durations[SEGMENTS[9].id]);
    await clickView(cdp, "home");
    await captureSegment(cdp, SEGMENTS[10], durations[SEGMENTS[10].id]);

    await buildVideo();
    console.log(`wrote ${path.join(OUT, "obol_demo_draft_v5.mp4")} (${frame} frames)`);
  } finally {
    cdp?.close();
    chrome.kill();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

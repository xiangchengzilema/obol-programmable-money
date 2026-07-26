import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "py-tts"))

import edge_tts  # noqa: E402

FFMPEG = ROOT / "tools" / "video-tools" / "node_modules" / "ffmpeg-static" / "ffmpeg.exe"
SEGMENTS = ROOT / "media" / "demo_draft" / "voiceover_v17_segments.json"
VIDEO = ROOT / "media" / "demo_draft" / "obol_demo_playwright_v16_final.mp4"
WORK = ROOT / "media" / "demo_draft" / "v17_edge_voiceover_work"
VOICE_WAV = ROOT / "media" / "demo_draft" / "obol_v17_edge_voiceover.wav"
OUT = ROOT / "media" / "demo_draft" / "obol_demo_v17_edge_voiceover.mp4"

VOICE = "en-US-GuyNeural"
RATE = "+0%"
VOLUME = "+0%"


def run(args, log_path=None):
    result = subprocess.run(
        [str(a) for a in args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if log_path:
        Path(log_path).write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(result.stdout + "\n" + result.stderr)
    return result.stdout + result.stderr


def media_duration(path: Path) -> float:
    result = subprocess.run(
        [str(FFMPEG), "-i", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = result.stdout + result.stderr
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", output)
    if not match:
        raise RuntimeError(f"Could not read duration for {path}")
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def atempo_chain(tempo: float) -> str:
    parts = []
    while tempo > 2.0:
        parts.append("atempo=2.0")
        tempo /= 2.0
    while tempo < 0.5:
        parts.append("atempo=0.5")
        tempo /= 0.5
    parts.append(f"atempo={tempo:.5f}")
    return ",".join(parts)


async def synthesize_segment(seg, mp3_path: Path):
    communicate = edge_tts.Communicate(
        text=seg["text"],
        voice=VOICE,
        rate=RATE,
        volume=VOLUME,
    )
    await communicate.save(str(mp3_path))


async def main():
    WORK.mkdir(parents=True, exist_ok=True)
    segments = json.loads(SEGMENTS.read_text(encoding="utf-8"))
    concat = WORK / "concat.txt"
    concat.write_text("", encoding="utf-8")

    for index, seg in enumerate(segments, start=1):
        stem = f"{index:02d}_{seg['id']}"
        raw_mp3 = WORK / f"{stem}_raw.mp3"
        fit_wav = WORK / f"{stem}_fit.wav"
        target = float(seg["end"]) - float(seg["start"])

        print(f"synth {stem}")
        await synthesize_segment(seg, raw_mp3)

        source = media_duration(raw_mp3)
        tempo = source / target
        filter_chain = (
            f"{atempo_chain(tempo)},"
            f"apad,atrim=0:{target},"
            "loudnorm=I=-16:TP=-1.5:LRA=11"
        )
        run(
            [
                FFMPEG,
                "-y",
                "-i",
                raw_mp3,
                "-filter:a",
                filter_chain,
                "-ar",
                "48000",
                "-ac",
                "2",
                fit_wav,
            ],
            WORK / f"{stem}_fit.log",
        )
        with concat.open("a", encoding="utf-8") as f:
            f.write(f"file '{fit_wav.name}'\n")
        print(f"  {source:.2f}s -> {target:.2f}s")

    run(
        [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", concat, "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", VOICE_WAV],
        WORK / "concat.log",
    )
    run(
        [
            FFMPEG,
            "-y",
            "-i",
            VIDEO,
            "-i",
            VOICE_WAV,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            OUT,
        ],
        WORK / "mux.log",
    )
    print(f"voice: {VOICE_WAV}")
    print(f"video: {OUT}")


if __name__ == "__main__":
    asyncio.run(main())

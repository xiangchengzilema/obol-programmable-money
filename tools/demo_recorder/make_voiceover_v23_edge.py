"""Build the final 99-second English voiceover with Edge TTS.

The output filename is consumed by ``tools/remotion/src/index_v23.jsx``.
Generated audio and scratch files stay under ignored media/public folders.
"""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import wave


ROOT = Path(__file__).resolve().parents[2]
FFMPEG = Path(os.environ.get(
    "OBOL_FFMPEG_PATH",
    ROOT / "tools" / "remotion" / "node_modules" / "@remotion"
    / "compositor-win32-x64-msvc" / "ffmpeg.exe",
))
WORK = ROOT / "media" / "demo_draft" / "voice_v23_edge"
PUBLIC = ROOT / "tools" / "remotion" / "public"
OUTPUT = PUBLIC / "obol_v23_edge_voiceover.wav"

SEGMENTS = [
    (8.0, "AI agents already read creator work, research posts, and paid knowledge sources. But most machine reads create no revenue for the people who produced the work."),
    (7.5, "Obol binds a current repository agent decision to a completed Circle transfer, then verifies the payer, token, recipient, amount, transaction hash, and block on Arc Testnet."),
    (7.5, "The buyer is not a human clicking subscribe. It is an autonomous research agent with a question, a budget, and a payment policy."),
    (9.5, "Before any U S D C moves, the agent evaluates sources, scores relevance, compares prices, checks cache reuse, and protects the remaining budget."),
    (9.5, "The anonymous playground is deliberately forced mock and labels its receipt as simulated. Paid content is released only for a confirmed live receipt, or an explicit mock demo receipt."),
    (8.0, "The decision log explains why the agent bought one source, skipped others, or reused a previous paid read."),
    (9.0, "In the marketplace, creators publish paid research with public previews. Full content stays locked until a valid payment is attached."),
    (9.0, "Creator Studio separates confirmed live earnings from simulated demo volume, pending attempts, and failed transfers, with an independent receipt trail for every creator."),
    (11.0, "For external agents, Obol exposes the same market through an X four oh two style HTTP payment flow. Request, receive a four oh two challenge, attach payment proof, and unlock the resource."),
    (12.0, "Obol began before this hackathon. This iteration added programmable spend guards, strict Arc proof verification, concurrency safe payment claims, honest settlement states, and forty six passing backend tests."),
    (8.0, "Obol makes machine reading accountable. Agents choose sources, Circle settles U S D C, Arc proves the read, and creators get paid."),
]


def run(*args):
    subprocess.run([str(part) for part in args], check=True)


def wav_duration(path):
    with wave.open(str(path), "rb") as audio:
        return audio.getnframes() / float(audio.getframerate())


def main():
    if not FFMPEG.exists():
        raise FileNotFoundError("Run npm ci in tools/remotion first")
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True, exist_ok=True)
    PUBLIC.mkdir(parents=True, exist_ok=True)
    fitted = []

    for index, (target, text) in enumerate(SEGMENTS, start=1):
        mp3 = WORK / f"{index:02d}.mp3"
        raw_wav = WORK / f"{index:02d}-raw.wav"
        fit_wav = WORK / f"{index:02d}-fit.wav"
        run(
            sys.executable, "-m", "edge_tts",
            "--voice", "en-US-GuyNeural",
            "--text", text,
            "--write-media", mp3,
        )
        run(FFMPEG, "-y", "-loglevel", "error", "-i", mp3,
            "-ar", "48000", "-ac", "2", raw_wav)
        natural = wav_duration(raw_wav)
        speaking_window = max(1.0, target - 0.35)
        speed = max(1.0, natural / speaking_window)
        audio_filter = (
            f"atempo={speed:.6f},apad,atrim=duration={target:.3f}"
        )
        run(FFMPEG, "-y", "-loglevel", "error", "-i", raw_wav,
            "-af", audio_filter, "-ar", "48000", "-ac", "2", fit_wav)
        fitted.append(fit_wav)

    concat_file = WORK / "concat.txt"
    concat_file.write_text(
        "\n".join(f"file '{path.as_posix()}'" for path in fitted) + "\n",
        encoding="utf-8",
    )
    run(FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
        "-i", concat_file, "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", OUTPUT)
    print(f"voiceover: {OUTPUT}")
    print(f"duration: {wav_duration(OUTPUT):.3f}s")


if __name__ == "__main__":
    main()

"""
IndexTTS2 adapter for Obol demo voiceover.

This script is intentionally API-based because, as of the current public
IndexTTS2 project page, stable inference code and weights are not available
from an official installable repository. Once an IndexTTS2 web UI or local
service is available, set:

  INDEXTTS2_ENDPOINT=http://127.0.0.1:7860/api/tts

Expected endpoint contract, one segment per request:
  POST JSON {
    "text": "...",
    "voice": "optional voice id or prompt name",
    "emotion": "calm, confident, product demo",
    "target_duration": 8.0
  }

Accepted response formats:
  1) audio/wav or audio/mpeg bytes
  2) JSON {"audio_url": "..."}
  3) JSON {"audio_base64": "..."}

The script normalizes each returned segment to the exact target duration,
then concatenates all segments into:
  media/demo_draft/obol_v21_indextts2_voiceover.wav
"""

import base64
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FFMPEG = ROOT / "tools" / "video-tools" / "node_modules" / "ffmpeg-static" / "ffmpeg.exe"
SEGMENTS = ROOT / "media" / "demo_draft" / "voiceover_v17_segments.json"
WORK = ROOT / "media" / "demo_draft" / "v21_indextts2_work"
OUT = ROOT / "media" / "demo_draft" / "obol_v21_indextts2_voiceover.wav"


def run(args, log_path=None, allow_error=False):
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
    if result.returncode != 0 and not allow_error:
        raise RuntimeError(result.stdout + "\n" + result.stderr)
    return result.stdout + result.stderr


def media_duration(path: Path) -> float:
    output = run([FFMPEG, "-i", path], allow_error=True)
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


def request_segment(endpoint: str, payload: dict, out_path: Path) -> None:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json,audio/*"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        content_type = resp.headers.get("Content-Type", "")
        data = resp.read()

    if content_type.startswith("audio/"):
        out_path.write_bytes(data)
        return

    try:
        parsed = json.loads(data.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"IndexTTS2 endpoint returned unsupported response: {content_type}") from exc

    if "audio_base64" in parsed:
        out_path.write_bytes(base64.b64decode(parsed["audio_base64"]))
        return

    if "audio_url" in parsed:
        with urllib.request.urlopen(parsed["audio_url"], timeout=180) as audio_resp:
            out_path.write_bytes(audio_resp.read())
        return

    raise RuntimeError("IndexTTS2 endpoint JSON must include audio_base64 or audio_url")


def main() -> None:
    endpoint = os.getenv("INDEXTTS2_ENDPOINT", "").strip()
    if not endpoint:
        print("INDEXTTS2_ENDPOINT is not set.")
        print("Remotion is already active. To replace the voice with IndexTTS2, expose an IndexTTS2 API and rerun:")
        print("  $env:INDEXTTS2_ENDPOINT='http://127.0.0.1:7860/api/tts'")
        print("  python .\\tools\\demo_recorder\\make_voiceover_v21_indextts2_adapter.py")
        sys.exit(2)

    WORK.mkdir(parents=True, exist_ok=True)
    segments = json.loads(SEGMENTS.read_text(encoding="utf-8"))
    concat = WORK / "concat.txt"
    concat.write_text("", encoding="utf-8")

    for index, seg in enumerate(segments, start=1):
        stem = f"{index:02d}_{seg['id']}"
        raw = WORK / f"{stem}_raw.audio"
        fit = WORK / f"{stem}_fit.wav"
        target = float(seg["end"]) - float(seg["start"])
        payload = {
            "text": seg["text"],
            "voice": os.getenv("INDEXTTS2_VOICE", "obol-demo-voice"),
            "emotion": os.getenv("INDEXTTS2_EMOTION", "calm, confident, clear product demo"),
            "target_duration": target,
        }
        print(f"IndexTTS2 synth {stem}: {target:.2f}s")
        request_segment(endpoint, payload, raw)
        source = media_duration(raw)
        tempo = source / target
        filters = f"{atempo_chain(tempo)},apad,atrim=0:{target},loudnorm=I=-16:TP=-1.5:LRA=11"
        run([FFMPEG, "-y", "-i", raw, "-filter:a", filters, "-ar", "48000", "-ac", "2", fit], WORK / f"{stem}.log")
        with concat.open("a", encoding="utf-8") as f:
            f.write(f"file '{fit.name}'\n")

    run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", concat, "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", OUT], WORK / "concat.log")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()

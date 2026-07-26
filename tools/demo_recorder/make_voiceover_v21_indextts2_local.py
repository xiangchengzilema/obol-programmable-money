import json
import shutil
import subprocess
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MEDIA_DIR = ROOT / "media" / "demo_draft"
TIMELINE_PATH = MEDIA_DIR / "voiceover_v17_segments.json"
FFMPEG_CANDIDATES = [
    ROOT / "tools" / "video-tools" / "node_modules" / "ffmpeg-static" / "ffmpeg.exe",
    ROOT / "tools" / "remotion" / "node_modules" / "@remotion" / "compositor-win32-x64-msvc" / "ffmpeg.exe",
    MEDIA_DIR / "ffmpeg_v9.exe",
]

INDEX_RUNTIME = Path(r"D:\arc-index-tts-runtime")
INDEX_PYTHON = INDEX_RUNTIME / ".venv" / "Scripts" / "python.exe"
INDEX_BATCH = INDEX_RUNTIME / "obol_v21_batch.jsonl"
INDEX_RAW = INDEX_RUNTIME / "obol_v21_indextts2_raw.wav"

FINAL_WAV = MEDIA_DIR / "obol_v21_indextts2_voiceover.wav"
REMOTION_PUBLIC_WAV = ROOT / "tools" / "remotion" / "public" / "obol_v21_indextts2_voiceover.wav"

TARGET_SECONDS = 99.0


def require_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)


def wav_duration_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        return wav.getnframes() / float(wav.getframerate())


def write_batch() -> None:
    segments = json.loads(TIMELINE_PATH.read_text(encoding="utf-8"))
    with INDEX_BATCH.open("w", encoding="utf-8") as handle:
        for index, segment in enumerate(segments):
            silence = 240 if index < len(segments) - 1 else 0
            row = {
                "text": segment["text"],
                "voice": "examples/voice_01.wav",
                "emotion_text": "professional, calm, confident product demo narration",
                "emotion_weight": "0.55",
                "silence_after_ms": silence,
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def atempo_filter(speed: float) -> str:
    # ffmpeg atempo accepts 0.5..100 in modern builds, but chaining keeps it portable.
    factors = []
    remaining = speed
    while remaining > 2.0:
        factors.append(2.0)
        remaining /= 2.0
    while remaining < 0.5:
        factors.append(0.5)
        remaining /= 0.5
    factors.append(remaining)
    return ",".join(f"atempo={factor:.6f}" for factor in factors)


def main() -> None:
    require_file(TIMELINE_PATH)
    require_file(INDEX_PYTHON)
    require_file(INDEX_RUNTIME / "examples" / "voice_01.wav")
    ffmpeg = next((path for path in FFMPEG_CANDIDATES if path.exists()), None)
    if ffmpeg is None:
        raise FileNotFoundError("No ffmpeg executable found")

    if not INDEX_RAW.exists():
        write_batch()

        cmd = [
            str(INDEX_PYTHON),
            "-m",
            "indextts.cli_v2",
            "batch",
            "--batch-file",
            str(INDEX_BATCH),
            "--model-dir",
            "checkpoints",
            "--device",
            "cuda",
            "--fp16",
            "--concat",
            "--output",
            str(INDEX_RAW),
            "--force",
        ]
        subprocess.run(cmd, cwd=str(INDEX_RUNTIME), check=True)
    else:
        print(f"reuse_raw={INDEX_RAW}")

    raw_duration = wav_duration_seconds(INDEX_RAW)
    speed = raw_duration / TARGET_SECONDS
    print(f"raw_duration={raw_duration:.3f}s target={TARGET_SECONDS:.3f}s speed={speed:.6f}")

    temp_output = MEDIA_DIR / "obol_v21_indextts2_voiceover.tmp.wav"
    subprocess.run(
        [
            str(ffmpeg),
            "-y",
            "-i",
            str(INDEX_RAW),
            "-filter:a",
            atempo_filter(speed),
            "-ar",
            "48000",
            "-ac",
            "2",
            str(temp_output),
        ],
        check=True,
    )
    temp_output.replace(FINAL_WAV)
    shutil.copyfile(FINAL_WAV, REMOTION_PUBLIC_WAV)

    final_duration = wav_duration_seconds(FINAL_WAV)
    print(f"final={FINAL_WAV}")
    print(f"final_duration={final_duration:.3f}s")
    print(f"remotion_public={REMOTION_PUBLIC_WAV}")


if __name__ == "__main__":
    main()

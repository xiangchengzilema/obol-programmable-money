import json
import re
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
]

INDEX_RUNTIME = Path(r"D:\arc-index-tts-runtime")
INDEX_PYTHON = INDEX_RUNTIME / ".venv" / "Scripts" / "python.exe"
INDEX_BATCH = INDEX_RUNTIME / "obol_v22_soft_batch.jsonl"
INDEX_RAW = INDEX_RUNTIME / "obol_v22_soft_raw.wav"
INDEX_VOICE = INDEX_RUNTIME / "examples" / "voice_07.wav"
INDEX_SEGMENT_DIR = INDEX_RUNTIME / "obol_v22_soft_segments"
INDEX_FIT_SEGMENT_DIR = INDEX_RUNTIME / "obol_v22_soft_segments_fit"
INDEX_CONCAT = INDEX_RUNTIME / "obol_v22_soft_concat.jsonl"

FINAL_WAV = MEDIA_DIR / "obol_v22_indextts2_soft_voiceover.wav"
REMOTION_PUBLIC_WAV = ROOT / "tools" / "remotion" / "public" / "obol_v22_indextts2_soft_voiceover.wav"

TARGET_SECONDS = 99.0
EMOTION_TEXT = "soft, friendly, trustworthy product demo narration"
EMOTION_WEIGHT = "0.22"


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
            silence = 220 if index < len(segments) - 1 else 0
            row = {
                "text": segment["text"],
                "voice": str(INDEX_VOICE),
                "emotion_text": EMOTION_TEXT,
                "emotion_weight": EMOTION_WEIGHT,
                "silence_after_ms": silence,
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def synthesize_segments() -> None:
    segments = json.loads(TIMELINE_PATH.read_text(encoding="utf-8"))
    INDEX_SEGMENT_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_FIT_SEGMENT_DIR.mkdir(parents=True, exist_ok=True)

    concat_rows = []
    for index, segment in enumerate(segments, start=1):
        segment_path = INDEX_SEGMENT_DIR / f"{index:02d}_{segment['id']}.wav"
        fit_segment_path = INDEX_FIT_SEGMENT_DIR / f"{index:02d}_{segment['id']}.wav"
        if not segment_path.exists() or segment_path.stat().st_size == 0:
            print(f"synth_segment={index:02d} id={segment['id']}")
            chunk_paths = synthesize_segment_chunks(index, segment)
            concat_audio(chunk_paths, segment_path, silence_after_ms=90)
        else:
            print(f"reuse_segment={segment_path}")

        silence = 220 if index < len(segments) else 0
        target_seconds = max(0.5, float(segment["end"]) - float(segment["start"]) - silence / 1000)
        fit_segment(segment_path, fit_segment_path, target_seconds)
        concat_rows.append({"audio": str(fit_segment_path), "silence_after_ms": silence})

    with INDEX_CONCAT.open("w", encoding="utf-8") as handle:
        for row in concat_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    subprocess.run(
        [
            str(INDEX_PYTHON),
            "-m",
            "indextts.cli_v2",
            "concat",
            "--concat-file",
            str(INDEX_CONCAT),
            "--output",
            str(INDEX_RAW),
            "--force",
        ],
        cwd=str(INDEX_RUNTIME),
        check=True,
    )


def sentence_chunks(text: str) -> list[str]:
    chunks = [chunk.strip() for chunk in re.findall(r"[^.!?]+[.!?]", text)]
    if not chunks:
        chunks = [text.strip()]
    return chunks


def synthesize_segment_chunks(index: int, segment: dict) -> list[Path]:
    chunks = sentence_chunks(segment["text"])
    output_paths = []
    for chunk_index, chunk_text in enumerate(chunks, start=1):
        chunk_path = INDEX_SEGMENT_DIR / f"{index:02d}_{segment['id']}_{chunk_index:02d}.wav"
        batch_path = INDEX_SEGMENT_DIR / f"{index:02d}_{segment['id']}_{chunk_index:02d}.jsonl"
        batch_row = {
            "text": chunk_text,
            "voice": str(INDEX_VOICE),
            "emotion_text": EMOTION_TEXT,
            "emotion_weight": EMOTION_WEIGHT,
            "silence_after_ms": 0,
        }
        batch_path.write_text(json.dumps(batch_row, ensure_ascii=False) + "\n", encoding="utf-8")

        if not chunk_path.exists() or chunk_path.stat().st_size == 0:
            print(f"  chunk={chunk_index:02d}/{len(chunks)}")
            subprocess.run(
                [
                    str(INDEX_PYTHON),
                    "-m",
                    "indextts.cli_v2",
                    "batch",
                    "--batch-file",
                    str(batch_path),
                    "--model-dir",
                    "checkpoints",
                    "--device",
                    "cuda",
                    "--fp16",
                    "--concat",
                    "--output",
                    str(chunk_path),
                    "--force",
                ],
                cwd=str(INDEX_RUNTIME),
                check=True,
            )
        output_paths.append(chunk_path)
    return output_paths


def concat_audio(audio_paths: list[Path], output_path: Path, silence_after_ms: int) -> None:
    concat_path = output_path.with_suffix(".concat.jsonl")
    with concat_path.open("w", encoding="utf-8") as handle:
        for index, audio_path in enumerate(audio_paths, start=1):
            silence = silence_after_ms if index < len(audio_paths) else 0
            handle.write(json.dumps({"audio": str(audio_path), "silence_after_ms": silence}, ensure_ascii=False) + "\n")

    subprocess.run(
        [
            str(INDEX_PYTHON),
            "-m",
            "indextts.cli_v2",
            "concat",
            "--concat-file",
            str(concat_path),
            "--output",
            str(output_path),
            "--force",
        ],
        cwd=str(INDEX_RUNTIME),
        check=True,
    )


def fit_segment(source_path: Path, output_path: Path, target_seconds: float) -> None:
    source_duration = wav_duration_seconds(source_path)
    speed = source_duration / target_seconds
    if output_path.exists() and output_path.stat().st_size > 0:
        current_duration = wav_duration_seconds(output_path)
        if abs(current_duration - target_seconds) <= 0.08:
            print(f"fit_reuse={output_path.name} duration={current_duration:.3f}s target={target_seconds:.3f}s")
            return

    print(
        f"fit_segment={source_path.name} raw={source_duration:.3f}s target={target_seconds:.3f}s speed={speed:.6f}"
    )
    ffmpeg = next((path for path in FFMPEG_CANDIDATES if path.exists()), None)
    if ffmpeg is None:
        raise FileNotFoundError("No ffmpeg executable found")

    subprocess.run(
        [
            str(ffmpeg),
            "-y",
            "-i",
            str(source_path),
            "-filter:a",
            atempo_filter(speed),
            "-ar",
            "22050",
            "-ac",
            "1",
            str(output_path),
        ],
        check=True,
    )


def atempo_filter(speed: float) -> str:
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
    require_file(INDEX_VOICE)
    ffmpeg = next((path for path in FFMPEG_CANDIDATES if path.exists()), None)
    if ffmpeg is None:
        raise FileNotFoundError("No ffmpeg executable found")

    write_batch()
    synthesize_segments()

    raw_duration = wav_duration_seconds(INDEX_RAW)
    speed = raw_duration / TARGET_SECONDS
    print(f"raw_duration={raw_duration:.3f}s target={TARGET_SECONDS:.3f}s speed={speed:.6f}")

    temp_output = MEDIA_DIR / "obol_v22_indextts2_soft_voiceover.tmp.wav"
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

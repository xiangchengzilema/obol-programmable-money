import json
import shutil
import subprocess
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MEDIA_DIR = ROOT / "media" / "demo_draft"
SAMPLE_DIR = MEDIA_DIR / "voice_samples"

INDEX_RUNTIME = Path(r"D:\arc-index-tts-runtime")
INDEX_PYTHON = INDEX_RUNTIME / ".venv" / "Scripts" / "python.exe"
INDEX_SAMPLE_DIR = INDEX_RUNTIME / "obol_voice_samples"

SAMPLE_TEXT = (
    "Obol lets AI agents pay creators per read with Circle Wallets on Arc Testnet. "
    "The agent chooses a useful source, pays USDC, and returns a receipt judges can verify."
)

VOICE_CANDIDATES = [
    {
        "name": "01_neutral_clear",
        "voice": "examples/voice_02.wav",
        "emotion_text": "calm, clear, neutral product demo narration",
        "emotion_weight": "0.20",
    },
    {
        "name": "02_soft_friendly",
        "voice": "examples/voice_07.wav",
        "emotion_text": "soft, friendly, trustworthy product demo narration",
        "emotion_weight": "0.22",
    },
    {
        "name": "03_calm_mature",
        "voice": "examples/voice_12.wav",
        "emotion_text": "calm, mature, professional startup demo narration",
        "emotion_weight": "0.18",
    },
    {
        "name": "04_low_energy_confident",
        "voice": "examples/voice_03.wav",
        "emotion_text": "low energy, confident, measured technical demo narration",
        "emotion_weight": "0.16",
    },
    {
        "name": "05_current_voice_less_force",
        "voice": "examples/voice_01.wav",
        "emotion_text": "calm, restrained, clear product demo narration",
        "emotion_weight": "0.12",
    },
]


def require_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)


def wav_duration_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        return wav.getnframes() / float(wav.getframerate())


def synthesize(candidate: dict) -> Path:
    final_output_path = SAMPLE_DIR / f"{candidate['name']}.wav"
    if final_output_path.exists() and final_output_path.stat().st_size > 0:
        return final_output_path

    batch_path = INDEX_SAMPLE_DIR / f"{candidate['name']}.jsonl"
    runtime_output_path = INDEX_SAMPLE_DIR / f"{candidate['name']}.wav"

    row = {
        "text": SAMPLE_TEXT,
        "voice": str(INDEX_RUNTIME / candidate["voice"]),
        "emotion_text": candidate["emotion_text"],
        "emotion_weight": candidate["emotion_weight"],
        "silence_after_ms": 0,
    }
    batch_path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")

    cmd = [
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
        str(runtime_output_path),
        "--force",
    ]
    subprocess.run(cmd, cwd=str(INDEX_RUNTIME), check=True)
    shutil.copyfile(runtime_output_path, final_output_path)
    return final_output_path


def main() -> None:
    require_file(INDEX_PYTHON)
    for candidate in VOICE_CANDIDATES:
        require_file(INDEX_RUNTIME / candidate["voice"])

    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

    manifest = []
    for candidate in VOICE_CANDIDATES:
        output_path = synthesize(candidate)
        manifest.append(
            {
                "name": candidate["name"],
                "path": str(output_path),
                "duration_seconds": round(wav_duration_seconds(output_path), 3),
                "voice": candidate["voice"],
                "emotion_text": candidate["emotion_text"],
                "emotion_weight": candidate["emotion_weight"],
            }
        )
        print(f"generated={output_path}")

    (SAMPLE_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"manifest={SAMPLE_DIR / 'manifest.json'}")


if __name__ == "__main__":
    main()

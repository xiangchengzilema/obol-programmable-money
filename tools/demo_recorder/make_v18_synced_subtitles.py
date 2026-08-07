import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FFMPEG = ROOT / "tools" / "video-tools" / "node_modules" / "ffmpeg-static" / "ffmpeg.exe"
SEGMENTS = ROOT / "media" / "demo_draft" / "voiceover_v17_segments.json"
VIDEO = ROOT / "media" / "demo_draft" / "obol_demo_playwright_v16_final.mp4"
AUDIO = ROOT / "media" / "demo_draft" / "obol_v17_edge_voiceover.wav"
OUT_DIR = ROOT / "media" / "demo_draft"

EN_ASS = OUT_DIR / "obol_v18_synced_en.ass"
BI_ASS = OUT_DIR / "obol_v18_synced_bilingual.ass"
OUT_EN = OUT_DIR / "obol_demo_v18_synced_voice_en.mp4"
OUT_BI = OUT_DIR / "obol_demo_v18_synced_voice_bilingual_review.mp4"

CN = {
    "01_problem": "AI 代理已经在阅读创作者内容；但大多数机器阅读没有给创作者带来收入。",
    "02_thesis": "Obol 把有价值的代理阅读转化为 USDC 付款、创作者收据和 Arc 交易证明。",
    "03_agent_buyer": "买方不是人在订阅，而是一个有问题、有预算、有付款策略的自主研究代理。",
    "04_before_payment": "付款前，代理会评估来源、相关性、价格、缓存复用，并保护剩余预算。",
    "05_settlement": "一个来源被选中后，Circle 提交钱包付款，创作者收到 USDC，Arc 返回结算证明。",
    "06_auditability": "决策日志解释代理为什么购买、跳过，或复用之前已付费的阅读。",
    "07_marketplace": "市场里，创作者发布带预览的付费研究；完整内容在付款前保持锁定。",
    "08_creator_side": "Creator Studio 展示卖方视角：付费阅读、收入、收据历史和独立收款轨迹。",
    "09_x402": "外部代理可通过 x402 风格 HTTP 支付流程请求、支付并解锁资源。",
    "10_traction": "Traction ledger 汇总运行、收据、付款状态、Circle 交易 ID 和 Arc txHash。",
    "11_closing": "Obol 让机器阅读可追责：代理选源，Circle 结算，Arc 证明，创作者收款。",
}

SHORT_EN = {
    "01_problem": "AI agents read creator work. Most machine reads still create no revenue.",
    "02_thesis": "Obol turns useful reads into USDC settlement, creator receipts, and Arc proof.",
    "03_agent_buyer": "The buyer is an autonomous agent with a question, a budget, and a payment policy.",
    "04_before_payment": "Before USDC moves, the agent scores relevance, compares prices, and checks cache reuse.",
    "05_settlement": "Circle submits the wallet payment; the creator receives USDC; Arc returns proof.",
    "06_auditability": "The decision log explains every buy, skip, and reuse decision.",
    "07_marketplace": "Creators publish paid research with previews. Full content stays locked until payment.",
    "08_creator_side": "Creator Studio shows paid reads, revenue, receipt history, and payout trails.",
    "09_x402": "x402 exposes the market to external agents through an HTTP-native payment flow.",
    "10_traction": "Each agent receipt shows creator, amount, Circle transaction id, and Arc txHash.",
    "11_closing": "Agents choose sources. Circle settles USDC. Arc verifies the transfer. Creators get paid.",
}


def ts(seconds: float) -> str:
    cs = round(seconds * 100)
    h = cs // 360000
    cs %= 360000
    m = cs // 6000
    cs %= 6000
    s = cs // 100
    c = cs % 100
    return f"{h}:{m:02d}:{s:02d}.{c:02d}"


def ass_escape(text: str) -> str:
    return text.replace("{", "(").replace("}", ")")


def wrap_ass(text: str, width: int = 62) -> str:
    words = text.split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return r"\N".join(lines[:2])


def write_ass(path: Path, bilingual: bool) -> None:
    segments = json.loads(SEGMENTS.read_text(encoding="utf-8"))
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1600
PlayResY: 900

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: EN, Arial, 42, &H00F5FBF8, &H000000FF, &H00101616, &HAA061012, -1, 0, 0, 0, 100, 100, 0, 0, 1, 3, 0, 2, 92, 92, 54, 1
Style: CN, Microsoft YaHei, 31, &H00D9E3DF, &H000000FF, &H00101616, &HAA061012, 0, 0, 0, 0, 100, 100, 0, 0, 1, 3, 0, 2, 92, 92, 20, 1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for seg in segments:
        start = ts(float(seg["start"]))
        end = ts(float(seg["end"]))
        en = ass_escape(wrap_ass(SHORT_EN[seg["id"]], 70))
        if bilingual:
            cn = ass_escape(CN[seg["id"]])
            events.append(f"Dialogue: 0,{start},{end},EN,,0,0,78,,{en}")
            events.append(f"Dialogue: 1,{start},{end},CN,,0,0,20,,{cn}")
        else:
            events.append(f"Dialogue: 0,{start},{end},EN,,0,0,54,,{en}")
    path.write_text(header + "\n".join(events) + "\n", encoding="utf-8-sig")


def run(args, log: Path) -> None:
    result = subprocess.run(
        [str(a) for a in args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    log.write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(result.stdout + "\n" + result.stderr)


def render(ass: Path, out: Path, bilingual: bool) -> None:
    ass_path = str(ass).replace("\\", "/").replace(":", r"\:")
    # Cover the old lower-left baked caption first, then burn the new synced timeline subtitles.
    height = 178 if bilingual else 128
    y = 900 - height
    vf = f"drawbox=x=0:y={y}:w=1600:h={height}:color=0x051012@0.82:t=fill,ass='{ass_path}'"
    run(
        [
            FFMPEG,
            "-y",
            "-i",
            VIDEO,
            "-i",
            AUDIO,
            "-filter:v",
            vf,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            out,
        ],
        OUT_DIR / f"{out.stem}_ffmpeg.log",
    )


def main() -> None:
    write_ass(EN_ASS, bilingual=False)
    write_ass(BI_ASS, bilingual=True)
    render(EN_ASS, OUT_EN, bilingual=False)
    render(BI_ASS, OUT_BI, bilingual=True)
    print(f"english: {OUT_EN}")
    print(f"bilingual: {OUT_BI}")


if __name__ == "__main__":
    main()

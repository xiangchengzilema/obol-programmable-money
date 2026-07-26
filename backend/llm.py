"""
Optional LLM helper. Uses OpenAI if OPENAI_API_KEY is set; otherwise returns
None and the agent falls back to a transparent heuristic. Never raises — any
failure returns None so the backend always runs (Codex needs it running).
"""
import os
import json
import urllib.request
import urllib.error


def _key():
    return os.getenv("OPENAI_API_KEY", "")


def available():
    return bool(_key())


def chat(system, user, max_tokens=700, temperature=0.2):
    key = _key()
    if not key:
        return None
    payload = json.dumps({
        "model": os.getenv("OBOL_LLM_MODEL", "gpt-4o-mini"),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]
    except Exception:
        return None


def chat_json(system, user, max_tokens=900):
    """Ask for JSON; parse leniently. Returns parsed object or None."""
    txt = chat(system, user + "\n\nRespond with ONLY valid JSON.", max_tokens=max_tokens)
    if not txt:
        return None
    txt = txt.strip()
    if txt.startswith("```"):
        txt = txt.strip("`")
        if txt.lower().startswith("json"):
            txt = txt[4:]
    start, end = txt.find("{"), txt.rfind("}")
    if start != -1 and end != -1:
        txt = txt[start:end + 1]
    try:
        return json.loads(txt)
    except Exception:
        return None

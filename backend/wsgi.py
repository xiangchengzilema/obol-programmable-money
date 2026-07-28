"""Production WSGI entrypoint for the public Obol demo.

The public deployment is mock-only by default. This prevents an anonymous
judge-facing website from ever gaining access to Circle wallet credentials by
accident. Set OBOL_PUBLIC_DEMO=0 only for a private, authenticated deployment.
"""

import os


if os.getenv("OBOL_PUBLIC_DEMO", "1").lower() in {"1", "true", "yes"}:
    os.environ["OBOL_PUBLIC_DEMO"] = "1"
    os.environ["OBOL_FORCE_MOCK"] = "1"
    os.environ.setdefault("OBOL_DISABLE_DEMO_RESET", "1")

from app import _ensure_seeded, app  # noqa: E402


_ensure_seeded()

"""
Obol backend API (Flask).
"Get paid when AI reads your work." Creators list articles behind a per-read
nanopaywall; an autonomous agent decides what to read, pays per article on Arc,
and returns an answer with receipts.

Run:  python app.py      (defaults to http://localhost:5001)
CORS is open so Codex's frontend (any port) can call it.
"""
import os
import time
import json
import shutil

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from flask import Flask, request, jsonify, send_from_directory

from db import init_db, get_db
from circle_service import CircleService
from wallet_pool import WalletPoolExhausted, pay_from_buyer_pool
from spending_policy import PolicyValidationError
import agent as agent_mod
import x402 as x402_mod
import llm
import seed


def _article_with_creator(cur, aid):
    return cur.execute("""SELECT a.*, c.name AS creator_name, c.payout_address
                          FROM articles a JOIN creators c ON c.id=a.creator_id
                          WHERE a.id=?""", (aid,)).fetchone()

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

app = Flask(__name__, static_folder=None)
init_db()


@app.after_request
def add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return resp


@app.route("/api/<path:_any>", methods=["OPTIONS"])
def preflight(_any):
    return ("", 204)


def err(msg, code=400):
    return jsonify({"error": msg}), code


def _env_flag(name, default="0"):
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _public_demo():
    return _env_flag("OBOL_PUBLIC_DEMO")


def safe_err(prefix, exc, code=502):
    if isinstance(exc, WalletPoolExhausted):
        return err(f"{prefix}: {exc}", 409)
    raw = str(exc).lower()
    if "insufficient token balance" in raw or "155258" in raw:
        return err(
            f"{prefix}: selected wallet does not have enough testnet USDC. "
            "Obol will use the funded buyer-wallet pool when available; fund another buyer wallet or choose a lower-priced source.",
            409,
        )
    msg = str(exc)
    for secret_name in ("CIRCLE_API_KEY", "CIRCLE_ENTITY_SECRET"):
        secret = os.getenv(secret_name, "")
        if secret:
            msg = msg.replace(secret, "[redacted]")
    if len(msg) > 500:
        msg = msg[:500] + "..."
    return err(f"{prefix}: {msg}", code)


@app.before_request
def public_demo_guard():
    """Keep the anonymous judge-facing service safe and repeatable.

    The production WSGI entrypoint already forces mock settlement. This request
    guard is a second fail-closed layer in case a host starts the app with a
    different command or accidentally adds Circle credentials.
    """
    if request.method == "OPTIONS" or not _public_demo():
        return None
    if CircleService().mode != "mock":
        return err(
            "public demo is misconfigured: live settlement is not allowed",
            503,
        )
    blocked_writes = {"/api/creators", "/api/articles", "/api/demo/reset"}
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.path in blocked_writes:
        return err("this management action is disabled in the public demo", 403)
    return None


def _ensure_seeded():
    """Seed demo data on first boot so hosted demos are usable immediately."""
    if os.getenv("OBOL_AUTO_SEED", "1") == "0":
        return
    conn = get_db()
    n = conn.execute("SELECT COUNT(*) FROM creators").fetchone()[0]
    conn.close()
    if n == 0:
        seed.seed(force=False)


# ----------------------------- meta -----------------------------
@app.get("/api/health")
def health():
    circle = CircleService()
    return jsonify({"status": "ok",
                    "public_demo": _public_demo(),
                    "settlement_mode": circle.mode,   # mock | live
                    "settlement_ready": circle.readiness()["ready_for_live_transfers"],
                    "llm_mode": "openai" if llm.available() else "heuristic"})


@app.get("/api/settlement/status")
def settlement_status():
    """Non-secret live settlement readiness. Safe to show in the UI."""
    return jsonify(CircleService().readiness())


@app.get("/api/stats")
def stats():
    """Traction counters for the dashboard / demo headline."""
    conn = get_db()
    c = conn.cursor()
    g = lambda q: c.execute(q).fetchone()[0]
    data = {
        "total_paid_usdc": round(g("SELECT COALESCE(SUM(amount_usdc),0) FROM receipts"), 6),
        "total_reads": g("SELECT COUNT(*) FROM receipts"),
        "live_paid_usdc": round(g(
            "SELECT COALESCE(SUM(amount_usdc),0) FROM receipts "
            "WHERE settlement_mode='live'"
        ), 6),
        "live_reads": g(
            "SELECT COUNT(*) FROM receipts WHERE settlement_mode='live'"
        ),
        "demo_paid_usdc": round(g(
            "SELECT COALESCE(SUM(amount_usdc),0) FROM receipts "
            "WHERE settlement_mode!='live'"
        ), 6),
        "demo_reads": g(
            "SELECT COUNT(*) FROM receipts WHERE settlement_mode!='live'"
        ),
        "num_creators": g("SELECT COUNT(*) FROM creators"),
        "num_articles": g("SELECT COUNT(*) FROM articles"),
        "num_runs": g("SELECT COUNT(*) FROM agent_runs"),
        # accountability counters: how much the agent reasoned, and what it saved
        "decisions_made": g("SELECT COUNT(*) FROM decisions"),
        "usdc_saved_by_reuse": round(
            g("SELECT COALESCE(SUM(price_usdc),0) FROM decisions WHERE decision='reuse'"), 6),
    }
    conn.close()
    return jsonify(data)


@app.get("/api/usage-daemon")
def usage_daemon_status():
    """Expose non-secret background usage-runner status for the live dashboard."""
    path = os.path.join(os.path.dirname(__file__), "usage_daemon_state.json")
    if not os.path.exists(path):
        return jsonify({"running": False, "available": False})
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return err("usage daemon state unreadable", 500)
    data["available"] = True
    return jsonify(data)


@app.post("/api/demo/reset")
def demo_reset():
    """Reset seed data for clean demo recordings.

    This keeps the hackathon demo repeatable: a fresh run shows new buy receipts
    instead of only cache reuses. Disable in production with OBOL_DISABLE_DEMO_RESET=1.
    """
    if os.getenv("OBOL_DISABLE_DEMO_RESET") == "1":
        return err("demo reset disabled", 403)
    d = request.get_json(force=True, silent=True) or {}
    conn = get_db()
    live_receipts = conn.execute(
        "SELECT COUNT(*) FROM receipts WHERE tx_hash LIKE '0x%'"
    ).fetchone()[0]
    usage_receipts = conn.execute(
        "SELECT COUNT(*) FROM receipts WHERE source IN ('usage-sim','evaluation-agent')"
    ).fetchone()[0]
    conn.close()
    usage_log = os.path.join(os.path.dirname(__file__), "usage_simulator_log.jsonl")
    has_usage_log = (
        os.getenv("OBOL_FORCE_MOCK") != "1"
        and os.path.exists(usage_log)
        and os.path.getsize(usage_log) > 0
    )
    if (CircleService().mode == "live" or has_usage_log) and (live_receipts or usage_receipts) and not d.get("confirm_live_reset"):
        return err(
            "database contains live/demo usage receipts; pass confirm_live_reset=true to reset",
            409,
        )
    backup_path = None
    db_path = os.path.join(os.path.dirname(__file__), "obol.db")
    if os.path.exists(db_path):
        backup_dir = os.path.join(os.path.dirname(__file__), "backups")
        os.makedirs(backup_dir, exist_ok=True)
        backup_path = os.path.join(backup_dir, f"obol-{time.strftime('%Y%m%d-%H%M%S')}-before-reset.db")
        shutil.copy2(db_path, backup_path)
    seed.seed(force=True)
    return jsonify({"status": "reset", "backup": backup_path})


# --------------------------- creators ---------------------------
@app.post("/api/creators")
def create_creator():
    d = request.get_json(force=True, silent=True) or {}
    name, addr = (d.get("name") or "").strip(), (d.get("payout_address") or "").strip()
    if not name:
        return err("name required")
    if not CircleService.valid_address(addr):
        return err("payout_address must be a 0x… 42-char address")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO creators(name, payout_address, created_at) VALUES(?,?,?)",
                (name, addr, time.time()))
    conn.commit()
    cid = cur.lastrowid
    row = dict(cur.execute("SELECT * FROM creators WHERE id=?", (cid,)).fetchone())
    conn.close()
    return jsonify(row), 201


@app.get("/api/creators")
def list_creators():
    conn = get_db()
    rows = [dict(r) for r in conn.execute("SELECT * FROM creators ORDER BY id").fetchall()]
    conn.close()
    return jsonify(rows)


@app.get("/api/creators/<int:cid>/earnings")
def creator_earnings(cid):
    conn = get_db()
    c = conn.cursor()
    creator = c.execute("SELECT * FROM creators WHERE id=?", (cid,)).fetchone()
    if not creator:
        conn.close()
        return err("creator not found", 404)
    pays = [dict(r) for r in c.execute("""
        SELECT r.*, a.title FROM receipts r JOIN articles a ON a.id=r.article_id
        WHERE r.creator_id=? ORDER BY r.id DESC""", (cid,)).fetchall()]
    total = round(sum(p["amount_usdc"] for p in pays), 6)
    conn.close()
    return jsonify({"creator": dict(creator), "total_earned_usdc": total,
                    "num_reads": len(pays), "payments": pays})


# --------------------------- articles ---------------------------
@app.post("/api/articles")
def create_article():
    d = request.get_json(force=True, silent=True) or {}
    try:
        creator_id = int(d["creator_id"])
        price = float(d["price_usdc"])
    except (KeyError, ValueError, TypeError):
        return err("creator_id (int) and price_usdc (number) required")
    title, content = (d.get("title") or "").strip(), (d.get("content") or "").strip()
    if not title or not content:
        return err("title and content required")
    if price < 0:
        return err("price_usdc must be >= 0")
    conn = get_db()
    cur = conn.cursor()
    if not cur.execute("SELECT 1 FROM creators WHERE id=?", (creator_id,)).fetchone():
        conn.close()
        return err("creator_id not found", 404)
    cur.execute("""INSERT INTO articles(creator_id, title, summary, content, price_usdc, tags, created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (creator_id, title, (d.get("summary") or "").strip(), content,
                 round(price, 6), (d.get("tags") or "").strip(), time.time()))
    conn.commit()
    aid = cur.lastrowid
    row = dict(cur.execute("SELECT * FROM articles WHERE id=?", (aid,)).fetchone())
    conn.close()
    return jsonify(row), 201


@app.get("/api/articles")
def list_articles():
    """Marketplace listing. Content is paywalled → only preview is returned."""
    q = (request.args.get("q") or "").strip().lower()
    conn = get_db()
    rows = conn.execute("""SELECT a.*, c.name AS creator_name FROM articles a
                           JOIN creators c ON c.id=a.creator_id ORDER BY a.id DESC""").fetchall()
    out = []
    for r in rows:
        r = dict(r)
        if q and q not in (r["title"] + " " + (r["tags"] or "") + " " + (r["summary"] or "")).lower():
            continue
        out.append({"id": r["id"], "creator_id": r["creator_id"], "creator_name": r["creator_name"],
                    "title": r["title"], "summary": r["summary"], "price_usdc": r["price_usdc"],
                    "tags": r["tags"], "preview": (r["content"][:160] + "…") if r["content"] else "",
                    "locked": True, "created_at": r["created_at"]})
    conn.close()
    return jsonify(out)


@app.get("/api/articles/<int:aid>")
def get_article(aid):
    """Single article — content stays locked (use /unlock or x402 to read it)."""
    conn = get_db()
    row = _article_with_creator(conn.cursor(), aid)
    conn.close()
    if not row:
        return err("article not found", 404)
    r = dict(row)
    return jsonify({"id": r["id"], "creator_id": r["creator_id"], "creator_name": r["creator_name"],
                    "title": r["title"], "summary": r["summary"], "price_usdc": r["price_usdc"],
                    "tags": r["tags"], "preview": (r["content"][:160] + "…") if r["content"] else "",
                    "locked": True, "created_at": r["created_at"]})


@app.post("/api/articles/<int:aid>/unlock")
def unlock_article(aid):
    """Direct buy: settle the per-read fee and return content plus a receipt."""
    d = request.get_json(force=True, silent=True) or {}
    buyer = (d.get("buyer") or "anon").strip()
    conn = get_db()
    row = _article_with_creator(conn.cursor(), aid)
    conn.close()
    if not row:
        return err("article not found", 404)
    art = dict(row)
    try:
        tx = pay_from_buyer_pool(
            CircleService(),
            art["payout_address"],
            art["price_usdc"],
            reference=f"unlock-{buyer[:18]}-{aid}",
            buyer_hint=buyer,
        )
    except Exception as e:
        return safe_err("settlement failed", e)
    receipt = x402_mod.grant(
        art,
        buyer,
        tx["tx_hash"],
        source="unlock",
        transaction_id=tx.get("transaction_id", ""),
        settlement_mode=tx.get("mode", CircleService().mode),
    )
    return jsonify({"article_id": aid, "title": art["title"], "creator_name": art["creator_name"],
                    "content": art["content"], "amount_paid_usdc": art["price_usdc"],
                    "payer_buyer_id": tx.get("payer_buyer_id", ""),
                    "payer_address": tx.get("payer_address", ""),
                    "receipt": receipt}), 201


@app.get("/api/creators/<int:cid>")
def get_creator(cid):
    conn = get_db()
    row = conn.execute("SELECT * FROM creators WHERE id=?", (cid,)).fetchone()
    conn.close()
    return jsonify(dict(row)) if row else err("creator not found", 404)


# ----------------------------- x402 -----------------------------
@app.get("/x402/articles/<int:aid>")
def x402_article(aid):
    """402 Payment Required → pay → retry with `X-Payment: <txhash>` to read."""
    conn = get_db()
    row = _article_with_creator(conn.cursor(), aid)
    conn.close()
    if not row:
        return err("article not found", 404)
    art = dict(row)
    circle = CircleService()
    proof = request.headers.get("X-Payment")
    if not proof:
        challenge = x402_mod.build_challenge(art)
        challenge["proofVerification"] = (
            "demo-format-only" if circle.mode == "mock"
            else "disabled-until-onchain-verification"
        )
        return jsonify(challenge), 402
    if circle.mode == "live" and not _env_flag("OBOL_ALLOW_UNVERIFIED_X402_PROOFS"):
        return err(
            "live x402 proof verification is not configured; "
            "refusing an unverified payment proof",
            501,
        )
    if not x402_mod.valid_proof(proof):
        return err("invalid X-Payment proof", 402)
    buyer = request.headers.get("X-Payer", "x402-agent")
    try:
        if _public_demo():
            receipt = x402_mod.demo_grant(art, buyer, proof)
        else:
            receipt = x402_mod.grant(
                art,
                buyer,
                proof,
                source="x402",
                settlement_mode=circle.mode,
            )
    except ValueError as e:
        return err(str(e), 402)
    return jsonify({"article_id": aid, "title": art["title"], "creator_name": art["creator_name"],
                    "content": art["content"], "receipt": receipt})


# ---------------------------- agent -----------------------------
@app.post("/api/agent/run")
def agent_run():
    d = request.get_json(force=True, silent=True) or {}
    query = (d.get("query") or "").strip()
    if not query:
        return err("query required")
    if len(query) > 1000:
        return err("query must be at most 1000 characters")
    try:
        budget = float(d.get("budget_usdc", 0.05))
    except (ValueError, TypeError):
        return err("budget_usdc must be a number")
    if budget <= 0:
        return err("budget_usdc must be > 0")
    if _public_demo():
        try:
            public_max_budget = float(
                os.getenv("OBOL_PUBLIC_MAX_BUDGET_USDC", "0.25")
            )
        except (TypeError, ValueError):
            public_max_budget = 0.25
        if budget > public_max_budget:
            return err(
                f"public demo budget must be <= {public_max_budget:.3f} USDC"
            )
    try:
        run = agent_mod.run_agent(query, budget, d.get("policy"))
    except PolicyValidationError as e:
        return err(str(e))
    except Exception as e:
        return safe_err("agent run failed", e)
    return jsonify(run), 201


@app.get("/api/agent/runs/<int:run_id>")
def get_run(run_id):
    run = agent_mod.get_run(run_id)
    return jsonify(run) if run else err("run not found", 404)


@app.get("/api/agent/runs")
def list_runs():
    conn = get_db()
    rows = [dict(r) for r in conn.execute(
        "SELECT id, query, budget_usdc, status, total_spent, created_at FROM agent_runs ORDER BY id DESC LIMIT 50"
    ).fetchall()]
    conn.close()
    return jsonify(rows)


# ---------------------------- ledger ----------------------------
@app.get("/api/ledger")
def ledger():
    conn = get_db()
    rows = [dict(r) for r in conn.execute("""
        SELECT r.*, a.title, c.name AS creator_name FROM receipts r
        JOIN articles a ON a.id=r.article_id JOIN creators c ON c.id=r.creator_id
        ORDER BY r.id DESC LIMIT 200""").fetchall()]
    conn.close()
    return jsonify(rows)


# ------------------------- frontend shell -------------------------
@app.get("/")
def frontend_index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.get("/<path:path>")
def frontend_asset(path):
    """Serve the static frontend from the same Flask app for one-URL demos."""
    target = os.path.join(FRONTEND_DIR, path)
    if os.path.isfile(target):
        return send_from_directory(FRONTEND_DIR, path)
    return send_from_directory(FRONTEND_DIR, "index.html")


if __name__ == "__main__":
    _ensure_seeded()
    port = int(os.getenv("PORT", os.getenv("FLASK_PORT", "5001")))
    print(f"[Obol] settlement={CircleService().mode}  llm={'openai' if llm.available() else 'heuristic'}")
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_DEBUG", "0") == "1")

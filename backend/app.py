"""
Obol backend API (Flask).
"Get paid when AI reads your work." Creators list articles behind a per-read
nanopaywall; an autonomous agent decides what to read, pays per article on Arc,
and returns an answer with receipts.

Run:  python app.py      (defaults to http://localhost:5001)
The public mock playground allows cross-origin judging. Private/live instances
are same-origin unless OBOL_ALLOWED_ORIGINS explicitly grants another origin.
"""
import os
import time
import json
import shutil
import hmac

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from flask import Flask, request, jsonify, send_from_directory

from db import init_db, get_db
from circle_service import CircleService
from wallet_pool import (
    SettlementOutcomeUnknown,
    WalletPoolExhausted,
    pay_from_buyer_pool,
)
from spending_policy import PolicyValidationError
import agent as agent_mod
import arc_verifier
import x402 as x402_mod
import llm
import seed


def _article_with_creator(cur, aid):
    return cur.execute("""SELECT a.*, c.name AS creator_name, c.payout_address
                          FROM articles a JOIN creators c ON c.id=a.creator_id
                          WHERE a.id=?""", (aid,)).fetchone()


def _claim_unlock_receipt(article, buyer, settlement_scope):
    """Atomically claim one direct unlock before any external transfer.

    The partial unique index in db.py makes this safe across threads and
    Gunicorn workers. A crashed or uncertain transfer stays pending instead of
    allowing a retry to double-pay.
    """
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        now = time.time()
        conn.execute(
            """DELETE FROM payment_claims
               WHERE claim_type='unlock' AND article_id=?
                 AND buyer_key=? AND settlement_scope=?
                 AND NOT EXISTS (
                   SELECT 1 FROM receipts r
                   WHERE r.id=payment_claims.receipt_id
                     AND r.article_id=payment_claims.article_id
                     AND r.source='unlock'
                     AND r.buyer=payment_claims.buyer_key
                     AND r.settlement_scope=payment_claims.settlement_scope
                     AND r.settlement_mode IN ('live','mock','pending')
                 )""",
            (article["id"], buyer, settlement_scope),
        )
        row = conn.execute(
            """SELECT r.* FROM payment_claims pc
               JOIN receipts r ON r.id=pc.receipt_id
               WHERE pc.claim_type='unlock' AND pc.article_id=?
                 AND pc.buyer_key=? AND pc.settlement_scope=?
                 AND r.article_id=pc.article_id AND r.source='unlock'
                 AND r.buyer=pc.buyer_key
                 AND r.settlement_scope=pc.settlement_scope
                 AND r.settlement_mode IN ('live','mock','pending')""",
            (article["id"], buyer, settlement_scope),
        ).fetchone()
        if row is not None:
            conn.commit()
            return dict(row), False

        # Adopt the strongest historical entitlement without rewriting audit
        # rows. A confirmed receipt must outrank a stale pending attempt.
        row = conn.execute(
            """SELECT * FROM receipts
               WHERE article_id=? AND buyer=? AND source='unlock'
                 AND settlement_scope=?
                 AND settlement_mode IN ('live','mock','pending')
               ORDER BY CASE settlement_mode
                          WHEN 'live' THEN 0 WHEN 'mock' THEN 0 ELSE 1 END,
                        id DESC LIMIT 1""",
            (article["id"], buyer, settlement_scope),
        ).fetchone()
        if row is not None:
            conn.execute(
                """INSERT INTO payment_claims(
                       claim_type, article_id, buyer_key, settlement_scope,
                       receipt_id, created_at, updated_at
                   ) VALUES('unlock',?,?,?,?,?,?)""",
                (article["id"], buyer, settlement_scope, row["id"], now, now),
            )
            conn.commit()
            return dict(row), False

        cur = conn.execute(
            """INSERT INTO receipts(
                   run_id, article_id, creator_id, amount_usdc, tx_hash,
                   transaction_id, blockchain, settlement_mode, settlement_scope,
                   source, buyer, created_at
               ) VALUES(NULL,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                article["id"], article["creator_id"], article["price_usdc"],
                "", "", "ARC-TESTNET", "pending", settlement_scope,
                "unlock", buyer, now,
            ),
        )
        receipt_id = cur.lastrowid
        conn.execute(
            """INSERT INTO payment_claims(
                   claim_type, article_id, buyer_key, settlement_scope,
                   receipt_id, created_at, updated_at
               ) VALUES('unlock',?,?,?,?,?,?)""",
            (article["id"], buyer, settlement_scope, receipt_id, now, now),
        )
        row = conn.execute(
            "SELECT * FROM receipts WHERE id=?", (receipt_id,)
        ).fetchone()
        conn.commit()
        return dict(row), True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _update_unlock_receipt(receipt_id, tx, settlement_mode):
    conn = get_db()
    conn.execute(
        """UPDATE receipts SET tx_hash=?, transaction_id=?, blockchain=?,
           settlement_mode=? WHERE id=?""",
        (
            tx.get("tx_hash", ""),
            tx.get("transaction_id", ""),
            tx.get("blockchain", "ARC-TESTNET"),
            settlement_mode,
            receipt_id,
        ),
    )
    if settlement_mode == "failed":
        conn.execute(
            "DELETE FROM payment_claims WHERE receipt_id=?", (receipt_id,)
        )
    conn.commit()
    row = conn.execute("SELECT * FROM receipts WHERE id=?", (receipt_id,)).fetchone()
    conn.close()
    return dict(row)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
LATEST_EVIDENCE_FILE = os.path.join(
    BASE_DIR, "evidence", "arc-testnet-agent-run-20260806.json"
)

app = Flask(__name__, static_folder=None)
init_db()


@app.after_request
def add_cors(resp):
    origin = request.headers.get("Origin", "")
    configured = {
        value.strip()
        for value in os.getenv("OBOL_ALLOWED_ORIGINS", "").split(",")
        if value.strip()
    }
    if _public_demo():
        resp.headers["Access-Control-Allow-Origin"] = "*"
    elif origin and origin in configured:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"
    if request.path.startswith("/x402/"):
        resp.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, X-Payment, X-Payer"
        )
    else:
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return resp


@app.route("/api/<path:_any>", methods=["OPTIONS"])
def preflight(_any):
    return ("", 204)


@app.route("/x402/<path:_any>", methods=["OPTIONS"])
def x402_preflight(_any):
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


def _load_latest_evidence():
    with open(LATEST_EVIDENCE_FILE, "r", encoding="utf-8") as evidence_file:
        evidence = json.load(evidence_file)
    if not isinstance(evidence, dict):
        raise ValueError("evidence bundle must be an object")
    return evidence


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


@app.before_request
def private_live_auth_guard():
    """Fail closed before any private live-mode mutation can spend funds."""
    if (
        request.method in {"GET", "HEAD", "OPTIONS"}
        or _public_demo()
        or getattr(CircleService(), "mode", "mock") != "live"
    ):
        return None
    expected = os.getenv("OBOL_LIVE_API_TOKEN", "")
    if not expected:
        return err(
            "live mutations are disabled until OBOL_LIVE_API_TOKEN is configured",
            503,
        )
    authorization = request.headers.get("Authorization", "")
    provided = authorization[7:] if authorization.startswith("Bearer ") else ""
    if not provided or not hmac.compare_digest(provided, expected):
        return err("valid bearer token required for live mutations", 401)
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


@app.get("/api/evidence/latest")
def latest_evidence():
    """Public, non-secret proof generated by this hackathon iteration."""
    try:
        return jsonify(_load_latest_evidence())
    except (OSError, json.JSONDecodeError, ValueError):
        return err("evaluation evidence is temporarily unavailable", 503)


@app.get("/api/arc/transactions/<tx_hash>/verify")
def verify_arc_transaction(tx_hash):
    """Strictly re-check the committed evaluation transaction on Arc Testnet."""
    try:
        if not arc_verifier.TX_HASH_RE.fullmatch(tx_hash):
            raise arc_verifier.InvalidTransactionHash(
                "tx_hash must be 0x followed by 64 hex characters"
            )
        evidence = _load_latest_evidence()
        expected_hash = str(evidence.get("arc", {}).get("transaction_hash", "")).lower()
        if tx_hash.lower() != expected_hash:
            return err("only the committed evaluation transaction can be verified", 404)
        return jsonify(arc_verifier.verify_evidence_bundle(evidence))
    except arc_verifier.InvalidTransactionHash as exc:
        return err(str(exc), 400)
    except arc_verifier.TransactionNotFound:
        return jsonify({
            "error": "transaction not found on Arc Testnet",
            "network": "arc-testnet",
            "tx_hash": tx_hash.lower(),
            "rpc_hosts": arc_verifier.rpc_hosts(),
        }), 404
    except (OSError, json.JSONDecodeError, ValueError):
        return err("evaluation evidence is temporarily unavailable", 503)
    except arc_verifier.ArcRPCError:
        return jsonify({
            "error": "Arc evidence verification is temporarily unavailable",
            "network": "arc-testnet",
            "rpc_hosts": arc_verifier.rpc_hosts(),
        }), 502


@app.get("/api/stats")
def stats():
    """Traction counters for the dashboard / demo headline."""
    conn = get_db()
    c = conn.cursor()
    g = lambda q: c.execute(q).fetchone()[0]
    live_paid = round(g(
        "SELECT COALESCE(SUM(amount_usdc),0) FROM receipts "
        "WHERE settlement_mode='live'"
    ), 6)
    live_reads = g(
        "SELECT COUNT(*) FROM receipts WHERE settlement_mode='live'"
    )
    demo_paid = round(g(
        "SELECT COALESCE(SUM(amount_usdc),0) FROM receipts "
        "WHERE settlement_mode='mock'"
    ), 6)
    demo_reads = g(
        "SELECT COUNT(*) FROM receipts WHERE settlement_mode='mock'"
    )
    data = {
        # Backwards-compatible headline names now mean confirmed live value.
        # Mock receipts are exposed separately and never called "paid".
        "total_paid_usdc": live_paid,
        "total_reads": live_reads,
        "live_paid_usdc": live_paid,
        "live_reads": live_reads,
        "demo_paid_usdc": demo_paid,
        "demo_reads": demo_reads,
        "settled_receipt_volume_usdc": round(live_paid + demo_paid, 6),
        "settled_receipts": live_reads + demo_reads,
        "unverified_paid_usdc": round(g(
            "SELECT COALESCE(SUM(amount_usdc),0) FROM receipts "
            "WHERE settlement_mode IN ('pending','failed','legacy')"
        ), 6),
        "unverified_reads": g(
            "SELECT COUNT(*) FROM receipts "
            "WHERE settlement_mode IN ('pending','failed','legacy')"
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
    live = [p for p in pays if p.get("settlement_mode") == "live"]
    demo = [p for p in pays if p.get("settlement_mode") == "mock"]
    settled = live + demo
    unverified = [p for p in pays if p.get("settlement_mode") not in {"live", "mock"}]
    total = round(sum(p["amount_usdc"] for p in live), 6)
    demo_total = round(sum(p["amount_usdc"] for p in demo), 6)
    conn.close()
    return jsonify({"creator": dict(creator), "total_earned_usdc": total,
                    "num_reads": len(live),
                    "demo_volume_usdc": demo_total,
                    "demo_reads": len(demo),
                    "settled_receipt_volume_usdc": round(total + demo_total, 6),
                    "payments": pays,
                    "settled_payments": settled,
                    "unverified_payments": unverified})


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
    circle = CircleService()
    try:
        receipt, owns_claim = _claim_unlock_receipt(art, buyer, circle.mode)
    except Exception as exc:
        return safe_err("could not reserve an idempotent payment claim", exc, 503)

    if not owns_claim:
        if (receipt["settlement_mode"] == "pending" and circle.mode == "live"
                and receipt.get("transaction_id")):
            try:
                current = circle.get_transaction(receipt["transaction_id"])
                normalized = {
                    "mode": "live",
                    "state": current.get("state"),
                    "tx_hash": current.get("txHash") or receipt.get("tx_hash", ""),
                }
                refreshed_mode = circle.settlement_mode_for_transaction(normalized, "live")
                if refreshed_mode != receipt["settlement_mode"]:
                    update_conn = get_db()
                    update_conn.execute(
                        "UPDATE receipts SET settlement_mode=?, tx_hash=? WHERE id=?",
                        (refreshed_mode, normalized["tx_hash"], receipt["id"]),
                    )
                    update_conn.commit()
                    update_conn.close()
                    receipt["settlement_mode"] = refreshed_mode
                    receipt["tx_hash"] = normalized["tx_hash"]
            except Exception:
                # The durable pending receipt is enough to prevent a duplicate
                # payment. A temporary Circle lookup failure must not unlock.
                pass
        if receipt["settlement_mode"] in {"live", "mock"}:
            return jsonify({
                "article_id": aid,
                "title": art["title"],
                "creator_name": art["creator_name"],
                "content": art["content"],
                "amount_paid_usdc": art["price_usdc"],
                "receipt": receipt,
                "reused_receipt": True,
            }), 200
        if receipt["settlement_mode"] == "failed":
            return jsonify({
                "error": "the recorded Circle transfer failed; content remains locked",
                "receipt": receipt,
            }), 409
        return jsonify({
            "status": "settlement_pending",
            "message": "Circle transfer submitted; content remains locked until COMPLETE",
            "article_id": aid,
            "title": art["title"],
            "creator_name": art["creator_name"],
            "amount_paid_usdc": art["price_usdc"],
            "receipt": receipt,
        }), 202

    try:
        tx = pay_from_buyer_pool(
            circle,
            art["payout_address"],
            art["price_usdc"],
            reference=f"unlock-{buyer[:18]}-{aid}",
            buyer_hint=buyer,
        )
    except WalletPoolExhausted as exc:
        receipt = _update_unlock_receipt(
            receipt["id"],
            {"state": "FAILED", "blockchain": "ARC-TESTNET"},
            "failed",
        )
        return safe_err("settlement failed", exc)
    except SettlementOutcomeUnknown as exc:
        return jsonify({
            "status": "settlement_pending",
            "message": "Settlement outcome unknown; durable claim kept pending",
            "article_id": aid,
            "title": art["title"],
            "creator_name": art["creator_name"],
            "amount_paid_usdc": art["price_usdc"],
            "receipt": receipt,
        }), 202
    except Exception as e:
        # Keep the durable claim pending. A network exception can happen after
        # an upstream accepted the transfer, so automatically clearing it would
        # make a retry capable of paying twice.
        return jsonify({
            "status": "settlement_pending",
            "message": "Settlement could not be proven; durable claim kept pending",
            "article_id": aid,
            "title": art["title"],
            "creator_name": art["creator_name"],
            "amount_paid_usdc": art["price_usdc"],
            "receipt": receipt,
        }), 202
    settlement_mode = circle.settlement_mode_for_transaction(tx, circle.mode)
    receipt = _update_unlock_receipt(receipt["id"], tx, settlement_mode)
    if settlement_mode == "pending":
        return jsonify({
            "status": "settlement_pending",
            "message": "Circle transfer submitted; content remains locked until COMPLETE",
            "article_id": aid,
            "title": art["title"],
            "creator_name": art["creator_name"],
            "amount_paid_usdc": art["price_usdc"],
            "receipt": receipt,
        }), 202
    if settlement_mode == "failed":
        return jsonify({
            "error": "Circle reported a failed transfer; content remains locked",
            "receipt": receipt,
        }), 409
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
@app.route(
    "/x402/articles/<int:aid>",
    methods=["GET"],
    provide_automatic_options=False,
)
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
                settlement_mode="mock" if circle.mode == "mock" else "legacy",
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

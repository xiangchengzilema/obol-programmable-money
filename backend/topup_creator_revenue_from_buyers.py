"""
Top up creator revenue using funded buyer wallets.

This is a live testnet utility: each payment is sent from a buyer Circle wallet
to the creator payout wallet and then recorded as a resource-bound receipt.
"""
import argparse
import json
import time

from db import get_db, init_db
from circle_service import CircleService
from usage_simulator import buyer_wallets


NATURAL_TARGETS = {
    "Alice Chen": 1.43,
    "DeFi Daily": 1.78,
    "Maya Okonkwo": 1.26,
    "The Arc Letter": 2.35,
    "Token Terminal Notes": 1.61,
    "StableLab Research": 1.92,
    "AgentOps Weekly": 1.37,
    "Rina Park": 2.08,
    "Northstar Protocols": 1.54,
}
SOURCE = "usage-sim"
CLAIM_TYPE = "usage"


def _money(value):
    return round(float(value or 0), 6)


def _current(conn):
    rows = conn.execute(
        """SELECT c.id, c.name, c.payout_address,
                  ROUND(COALESCE(SUM(CASE WHEN r.settlement_mode='live'
                       AND r.settlement_scope='live' THEN r.amount_usdc ELSE 0 END),0), 6)
                       AS earned_usdc,
                  ROUND(COALESCE(SUM(CASE WHEN r.settlement_mode='live'
                       AND r.settlement_scope='live' THEN r.amount_usdc ELSE 0 END),0), 6)
                       AS live_earned_usdc,
                  ROUND(COALESCE(SUM(CASE WHEN r.settlement_mode='mock'
                       AND r.settlement_scope='mock' THEN r.amount_usdc ELSE 0 END),0), 6)
                       AS mock_earned_usdc,
                  COUNT(CASE WHEN r.settlement_mode='live'
                       AND r.settlement_scope='live' THEN 1 END) AS receipts,
                  ROUND(COALESCE(SUM(CASE WHEN r.settlement_mode='pending'
                       AND r.settlement_scope='live' THEN r.amount_usdc ELSE 0 END),0), 6)
                       AS pending_usdc,
                  COUNT(CASE WHEN r.settlement_mode='pending'
                       AND r.settlement_scope='live' THEN 1 END) AS pending_receipts,
                  ROUND(COALESCE(SUM(CASE WHEN r.settlement_mode IN ('pending','failed','legacy')
                       OR (r.settlement_mode='live' AND r.settlement_scope<>'live')
                       OR (r.settlement_mode='mock' AND r.settlement_scope<>'mock')
                       THEN r.amount_usdc ELSE 0 END),0), 6) AS unverified_usdc,
                  COUNT(CASE WHEN r.settlement_mode IN ('pending','failed','legacy')
                       OR (r.settlement_mode='live' AND r.settlement_scope<>'live')
                       OR (r.settlement_mode='mock' AND r.settlement_scope<>'mock')
                       THEN 1 END) AS unverified_receipts
           FROM creators c LEFT JOIN receipts r ON r.creator_id=c.id
           GROUP BY c.id
           ORDER BY c.id"""
    ).fetchall()
    return [dict(r) for r in rows]


def _ensure_article(conn, creator, amount):
    title = f"Live buyer top-up: {creator['name']} creator revenue proof"
    row = conn.execute(
        "SELECT * FROM articles WHERE creator_id=? AND title=?",
        (creator["id"], title),
    ).fetchone()
    if row:
        return dict(row)
    conn.execute(
        """INSERT INTO articles(creator_id, title, summary, content, price_usdc, tags, created_at)
           VALUES(?,?,?,?,?,?,?)""",
        (
            creator["id"],
            title,
            "A live testnet paid read from a funded buyer wallet.",
            (
                f"{creator['name']} receives a live Arc testnet paid read from a buyer "
                "wallet. This record exists to stress-test creator payout accounting, "
                "wallet execution, and txHash-backed receipts before the hackathon demo."
            ),
            amount,
            "live-testnet,buyer-wallet,creator-revenue,arc",
            time.time(),
        ),
    )
    conn.commit()
    return dict(conn.execute(
        "SELECT * FROM articles WHERE creator_id=? AND title=?",
        (creator["id"], title),
    ).fetchone())


def _claim_payment(conn, article, creator, buyer, amount):
    """Atomically reserve this article/buyer/live payment before Circle I/O."""
    buyer_id = buyer["buyer_id"]
    now = time.time()
    conn.execute("BEGIN IMMEDIATE")
    try:
        claim = conn.execute(
            """SELECT r.* FROM payment_claims p
               JOIN receipts r ON r.id=p.receipt_id
               WHERE p.claim_type=? AND p.article_id=? AND p.buyer_key=?
                 AND p.settlement_scope='live'""",
            (CLAIM_TYPE, article["id"], buyer_id),
        ).fetchone()
        if claim:
            conn.commit()
            return dict(claim), False

        existing = conn.execute(
            """SELECT * FROM receipts
               WHERE article_id=? AND creator_id=? AND buyer=? AND source=?
                 AND settlement_scope='live' AND settlement_mode<>'legacy'
               ORDER BY CASE WHEN settlement_mode='live' THEN 0
                              WHEN settlement_mode='pending' THEN 1
                              ELSE 2 END, id DESC LIMIT 1""",
            (article["id"], creator["id"], buyer_id, SOURCE),
        ).fetchone()
        if existing:
            receipt_id = existing["id"]
        else:
            cur = conn.execute(
                """INSERT INTO receipts(run_id, article_id, creator_id, amount_usdc,
                   tx_hash, transaction_id, blockchain, settlement_mode,
                   settlement_scope, source, buyer, created_at)
                   VALUES(NULL,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    article["id"], creator["id"], amount, "", "",
                    "ARC-TESTNET", "pending", "live", SOURCE, buyer_id, now,
                ),
            )
            receipt_id = cur.lastrowid
        conn.execute(
            """INSERT OR IGNORE INTO payment_claims(
               claim_type, article_id, buyer_key, settlement_scope,
               receipt_id, created_at, updated_at)
               VALUES(?,?,?,?,?,?,?)""",
            (CLAIM_TYPE, article["id"], buyer_id, "live", receipt_id, now, now),
        )
        claim = conn.execute(
            """SELECT r.* FROM payment_claims p
               JOIN receipts r ON r.id=p.receipt_id
               WHERE p.claim_type=? AND p.article_id=? AND p.buyer_key=?
                 AND p.settlement_scope='live'""",
            (CLAIM_TYPE, article["id"], buyer_id),
        ).fetchone()
        conn.commit()
        return dict(claim), existing is None and claim["id"] == receipt_id
    except Exception:
        conn.rollback()
        raise


def _update_claim(conn, receipt_id, settlement_mode, tx=None):
    tx = tx if isinstance(tx, dict) else {}
    conn.execute(
        """UPDATE receipts
           SET tx_hash=?, transaction_id=?, blockchain=?, settlement_mode=?
           WHERE id=?""",
        (
            tx.get("tx_hash", ""), tx.get("transaction_id", ""),
            tx.get("blockchain", "ARC-TESTNET"), settlement_mode, receipt_id,
        ),
    )
    conn.execute(
        "UPDATE payment_claims SET updated_at=? WHERE receipt_id=?",
        (time.time(), receipt_id),
    )
    conn.commit()


def _definitely_insufficient(exc):
    message = str(exc).lower()
    return "insufficient" in message or "155258" in message


def run(targets, buyer_start, buyer_end, dry_run=False):
    init_db()
    conn = get_db()
    buyers = [
        w for w in buyer_wallets()
        if buyer_start <= int(w["buyer_id"].split("-")[-1]) <= buyer_end
    ]
    if not buyers:
        raise SystemExit("No buyer wallets selected.")
    circle = CircleService()
    if not dry_run and circle.mode != "live":
        raise SystemExit("Circle live mode is not configured.")

    payments = []
    buyer_idx = 0
    for creator in _current(conn):
        target = targets.get(creator["name"], 1.05)
        missing = _money(target - creator["earned_usdc"])
        if missing <= 0:
            continue
        amount = max(0.01, missing)
        buyer = buyers[buyer_idx % len(buyers)]
        buyer_idx += 1
        item = {
            "creator": creator["name"],
            "buyer": buyer["buyer_id"],
            "amount_usdc": amount,
            "target_usdc": target,
            "before_usdc": creator["earned_usdc"],
        }
        if dry_run:
            item["status"] = "dry-run"
            item["article"] = "would create/reuse live buyer top-up article"
            payments.append(item)
            continue
        article = _ensure_article(conn, creator, amount)
        item["article_id"] = article["id"]
        tx = None
        errors = []
        blocked_by_pending = False
        for attempt in range(len(buyers)):
            selected = buyers[(buyer_idx - 1 + attempt) % len(buyers)]
            receipt, owned = _claim_payment(conn, article, creator, selected, amount)
            if not owned:
                mode = receipt.get("settlement_mode", "pending")
                errors.append({
                    "buyer": selected["buyer_id"],
                    "status": mode,
                    "error": "existing payment claim",
                })
                if mode == "pending":
                    # An earlier request may already have reached Circle.  Never
                    # switch payer wallets while that outcome is unknown.
                    buyer = selected
                    item["buyer"] = selected["buyer_id"]
                    item["status"] = "pending"
                    item["settlement_mode"] = "pending"
                    item["transaction_id"] = receipt.get("transaction_id", "")
                    item["tx_hash"] = receipt.get("tx_hash", "")
                    blocked_by_pending = True
                    break
                # A settled claim already contributed to _current(); if the
                # target was raised, a different buyer can fund the increment.
                # A definite failed claim is likewise safe to skip.
                continue
            try:
                tx = circle.send_usdc_from_wallet(
                    selected["wallet_id"],
                    creator["payout_address"],
                    amount,
                    reference=f"obol-buyer-topup-{selected['buyer_id']}-{creator['id']}",
                )
                buyer = selected
                item["buyer"] = buyer["buyer_id"]
                settlement_mode = circle.settlement_mode_for_transaction(tx, circle.mode)
                _update_claim(conn, receipt["id"], settlement_mode, tx)
                if settlement_mode == "pending":
                    item["status"] = "pending"
                    item["settlement_mode"] = "pending"
                    blocked_by_pending = True
                    break
                if settlement_mode != "live":
                    errors.append({
                        "buyer": selected["buyer_id"],
                        "status": settlement_mode,
                        "error": "Circle did not return a live settled transfer",
                    })
                    tx = None
                    continue
                break
            except Exception as exc:
                errors.append({"buyer": selected["buyer_id"], "error": str(exc)[:220]})
                if _definitely_insufficient(exc):
                    _update_claim(conn, receipt["id"], "failed")
                    continue
                # The claim was persisted before Circle was called.  Preserve
                # it as pending and stop immediately: choosing another wallet
                # here could double-pay after a lost/timeout response.
                buyer = selected
                item["buyer"] = selected["buyer_id"]
                item["status"] = "pending"
                item["settlement_mode"] = "pending"
                blocked_by_pending = True
                break
        if blocked_by_pending:
            item["errors"] = errors
            payments.append(item)
            continue
        if tx is None:
            item["status"] = "error"
            item["settlement_mode"] = "failed"
            item["errors"] = errors
            payments.append(item)
            continue
        item.update({
            "status": tx.get("state", "submitted"),
            "settlement_mode": settlement_mode,
            "tx_hash": tx.get("tx_hash", ""),
            "transaction_id": tx.get("transaction_id", ""),
        })
        payments.append(item)

    summary = _current(conn)
    conn.close()
    return {"dry_run": dry_run, "payments": payments, "summary": summary}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--buyer-start", type=int, default=1)
    parser.add_argument("--buyer-end", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(
        run(NATURAL_TARGETS, args.buyer_start, args.buyer_end, args.dry_run),
        indent=2,
        ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()

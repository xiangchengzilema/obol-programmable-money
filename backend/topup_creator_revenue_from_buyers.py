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


def _money(value):
    return round(float(value or 0), 6)


def _current(conn):
    rows = conn.execute(
        """SELECT c.id, c.name, c.payout_address,
                  ROUND(COALESCE(SUM(r.amount_usdc),0), 6) AS earned_usdc,
                  COUNT(r.id) AS receipts
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
        for attempt in range(len(buyers)):
            selected = buyers[(buyer_idx - 1 + attempt) % len(buyers)]
            try:
                tx = circle.send_usdc_from_wallet(
                    selected["wallet_id"],
                    creator["payout_address"],
                    amount,
                    reference=f"obol-buyer-topup-{selected['buyer_id']}-{creator['id']}",
                )
                buyer = selected
                item["buyer"] = buyer["buyer_id"]
                break
            except Exception as exc:
                errors.append({"buyer": selected["buyer_id"], "error": str(exc)[:220]})
        if tx is None:
            item["status"] = "error"
            item["errors"] = errors
            payments.append(item)
            continue
        conn.execute(
            """INSERT INTO receipts(run_id, article_id, creator_id, amount_usdc,
               tx_hash, transaction_id, blockchain, source, buyer, created_at)
               VALUES(NULL,?,?,?,?,?,?,?,?,?)""",
            (
                article["id"],
                creator["id"],
                amount,
                tx.get("tx_hash", ""),
                tx.get("transaction_id", ""),
                tx.get("blockchain", "ARC-TESTNET"),
                "usage-sim",
                buyer["buyer_id"],
                time.time(),
            ),
        )
        conn.commit()
        item.update({
            "status": tx.get("state", "submitted"),
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

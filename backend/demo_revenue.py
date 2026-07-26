"""
Create clearly labelled demo/evaluation revenue for every creator.

This is for hackathon testnet evidence, not fake traction. It can:

1. Non-destructively enrich the marketplace to the full seeded catalog.
2. Optionally create distinct Circle payout wallets for creators.
3. Add one premium "evaluation bundle" article per creator if needed.
4. Pay enough testnet USDC so every creator shows >= target revenue.

Run dry:
  python demo_revenue.py --dry-run

Run live testnet:
  python demo_revenue.py --live --create-creator-wallets
"""
import argparse
import json
import time
from pathlib import Path

from db import init_db, get_db
from circle_service import CircleService
import enrich_demo


TARGET_USDC = 1.01
SOURCE = "evaluation-agent"
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
BUYERS = [
    "atlas-evaluator-wallet",
    "nova-research-wallet",
    "quartz-agent-wallet",
    "mira-buyer-wallet",
    "northstar-review-wallet",
    "cipher-reader-wallet",
    "signal-scout-wallet",
    "orbit-analyst-wallet",
    "proof-lab-wallet",
]
WALLETS_FILE = Path(__file__).with_name("demo_creator_wallets.json")


def _money(value):
    return round(float(value or 0), 6)


def _placeholder_address(addr):
    """Seed addresses are obvious placeholders: 0x111..., 0x222..., etc."""
    if not addr or len(addr) != 42 or not addr.startswith("0x"):
        return True
    body = addr[2:]
    return len(set(body)) == 1


def _load_wallet_map():
    if not WALLETS_FILE.exists():
        return {}
    try:
        return json.loads(WALLETS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_wallet_map(data):
    WALLETS_FILE.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _creator_rows(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM creators ORDER BY id").fetchall()]


def _earned_by_creator(conn):
    rows = conn.execute("""
        SELECT c.id, COALESCE(SUM(r.amount_usdc), 0) AS earned, COUNT(r.id) AS receipts
        FROM creators c LEFT JOIN receipts r ON r.creator_id = c.id
        GROUP BY c.id
    """).fetchall()
    return {r["id"]: {"earned": _money(r["earned"]), "receipts": r["receipts"]} for r in rows}


def _ensure_creator_wallets(conn, circle, replace_placeholders=True):
    wallet_map = _load_wallet_map()
    updates = []
    for creator in _creator_rows(conn):
        cid = str(creator["id"])
        if cid in wallet_map and wallet_map[cid].get("address"):
            address = wallet_map[cid]["address"]
        elif replace_placeholders and _placeholder_address(creator["payout_address"]):
            wallet = circle.create_wallet(label=f"creator-{creator['id']}-{creator['name'][:16]}")
            wallet_map[cid] = {
                "creator_id": creator["id"],
                "creator_name": creator["name"],
                "wallet_id": wallet.get("id"),
                "address": wallet.get("address"),
                "blockchain": wallet.get("blockchain"),
                "state": wallet.get("state"),
                "created_at": time.time(),
            }
            address = wallet["address"]
        else:
            continue
        if address and address != creator["payout_address"]:
            conn.execute("UPDATE creators SET payout_address=? WHERE id=?", (address, creator["id"]))
            updates.append((creator["name"], address))
    conn.commit()
    if updates:
        _save_wallet_map(wallet_map)
    return updates


def _ensure_bundle_article(conn, creator, price):
    title = f"Evaluation bundle: {creator['name']} paid research brief"
    row = conn.execute(
        "SELECT * FROM articles WHERE creator_id=? AND title=?",
        (creator["id"], title),
    ).fetchone()
    if row:
        return dict(row)
    summary = "A premium paid read used by Obol evaluation agents to prove creator revenue settlement."
    content = (
        f"This paid research brief belongs to {creator['name']}. It is intentionally "
        "labelled as an evaluation bundle so hackathon judges can inspect revenue, "
        "receipt binding, and Arc testnet settlement without mistaking this for "
        "organic production traction. The important product behavior is that an "
        "agent can select a priced source, pay USDC, unlock the content, and leave "
        "a creator-visible receipt."
    )
    conn.execute(
        """INSERT INTO articles(creator_id, title, summary, content, price_usdc, tags, created_at)
           VALUES(?,?,?,?,?,?,?)""",
        (creator["id"], title, summary, content, price, "demo,evaluation,creator-revenue", time.time()),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM articles WHERE creator_id=? AND title=?", (creator["id"], title)).fetchone())


def _target_for(creator_name, target_usdc, profile):
    if profile == "natural":
        return _money(NATURAL_TARGETS.get(creator_name, target_usdc))
    return _money(target_usdc)


def _ensure_topup_article(conn, creator, price, target):
    title = f"Evaluation follow-up: {creator['name']} reached ${target:.2f}"
    row = conn.execute(
        "SELECT * FROM articles WHERE creator_id=? AND title=?",
        (creator["id"], title),
    ).fetchone()
    if row:
        return dict(row)
    summary = "A follow-up paid read used to create varied, realistic-looking evaluation revenue."
    content = (
        f"{creator['name']} received an additional evaluation paid read. This entry "
        "keeps the demo ledger varied: creators do not all earn the same amount, "
        "while every transaction remains labelled as testnet evaluation activity."
    )
    conn.execute(
        """INSERT INTO articles(creator_id, title, summary, content, price_usdc, tags, created_at)
           VALUES(?,?,?,?,?,?,?)""",
        (creator["id"], title, summary, content, price, "demo,evaluation,revenue-variance", time.time()),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM articles WHERE creator_id=? AND title=?", (creator["id"], title)).fetchone())


def build_plan(target_usdc=TARGET_USDC, profile="floor"):
    init_db()
    enrich_demo.enrich()
    conn = get_db()
    earned = _earned_by_creator(conn)
    rows = []
    for creator in _creator_rows(conn):
        current = earned.get(creator["id"], {"earned": 0, "receipts": 0})
        target = _target_for(creator["name"], target_usdc, profile)
        missing = max(0.0, target - current["earned"])
        rows.append({
            "creator_id": creator["id"],
            "creator": creator["name"],
            "target_usdc": target,
            "current_usdc": _money(current["earned"]),
            "receipts": current["receipts"],
            "needed_usdc": _money(missing),
            "payout_address": creator["payout_address"],
        })
    conn.close()
    return rows


def execute(target_usdc=TARGET_USDC, live=False, create_creator_wallets=False, profile="floor"):
    init_db()
    enrich_demo.enrich()
    circle = CircleService()
    if live and circle.mode != "live":
        raise SystemExit("Live mode requested, but Circle is not configured. Check backend/.env.")

    conn = get_db()
    wallet_updates = []
    if live and create_creator_wallets:
        wallet_updates = _ensure_creator_wallets(conn, circle)

    creators = _creator_rows(conn)
    earned = _earned_by_creator(conn)
    payments = []
    for idx, creator in enumerate(creators):
        current = earned.get(creator["id"], {"earned": 0, "receipts": 0})
        target = _target_for(creator["name"], target_usdc, profile)
        needed = _money(max(0.0, target - current["earned"]))
        if needed <= 0:
            continue
        price = _money(needed)
        article = (_ensure_bundle_article(conn, creator, price)
                   if current["earned"] <= 0
                   else _ensure_topup_article(conn, creator, price, target))
        buyer = BUYERS[idx % len(BUYERS)]

        if not live:
            payments.append({
                "creator": creator["name"],
                "status": "dry-run",
                "amount_usdc": price,
                "article": article["title"],
                "buyer": buyer,
                "payout_address": creator["payout_address"],
            })
            continue

        tx = circle.send_usdc(creator["payout_address"], price, reference=f"obol-eval-{creator['id']}")
        conn.execute(
            """INSERT INTO receipts(run_id, article_id, creator_id, amount_usdc,
               tx_hash, transaction_id, blockchain, source, buyer, created_at)
               VALUES(NULL,?,?,?,?,?,?,?,?,?)""",
            (
                article["id"],
                creator["id"],
                price,
                tx.get("tx_hash", ""),
                tx.get("transaction_id", ""),
                tx.get("blockchain", "ARC-TESTNET"),
                SOURCE,
                buyer,
                time.time(),
            ),
        )
        conn.commit()
        payments.append({
            "creator": creator["name"],
            "status": tx.get("state", "submitted"),
            "amount_usdc": price,
            "article": article["title"],
            "buyer": buyer,
            "tx_hash": tx.get("tx_hash", ""),
            "transaction_id": tx.get("transaction_id", ""),
            "payout_address": creator["payout_address"],
        })

    summary = []
    refreshed = _earned_by_creator(conn)
    for creator in _creator_rows(conn):
        row = refreshed.get(creator["id"], {"earned": 0, "receipts": 0})
        creator_target = _target_for(creator["name"], target_usdc, profile)
        summary.append({
            "creator": creator["name"],
            "earned_usdc": _money(row["earned"]),
            "receipts": row["receipts"],
            "target_usdc": creator_target,
            "target_met": row["earned"] >= creator_target,
        })
    conn.close()
    return {"live": live, "wallet_updates": wallet_updates, "payments": payments, "summary": summary}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=float, default=TARGET_USDC)
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen; default if --live is omitted.")
    parser.add_argument("--live", action="store_true", help="Send real testnet USDC via Circle.")
    parser.add_argument("--create-creator-wallets", action="store_true", help="Create distinct Circle payout wallets for placeholder creators.")
    parser.add_argument("--profile", choices=["floor", "natural"], default="floor",
                        help="floor gives everyone the same minimum target; natural uses varied demo targets.")
    args = parser.parse_args()

    if not args.live:
        print(json.dumps({"plan": build_plan(args.target, args.profile)}, indent=2, ensure_ascii=False))
        return
    print(json.dumps(execute(args.target, live=True,
                             create_creator_wallets=args.create_creator_wallets,
                             profile=args.profile),
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

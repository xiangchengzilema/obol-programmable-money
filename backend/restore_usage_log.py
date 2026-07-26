"""
Restore local demo state from the usage simulator append-only log.

The real Arc/Circle transfers live outside SQLite. This script rebuilds the
local display database after an accidental demo reset by replaying logged
paid-read receipts with their original tx hashes and buyer ids.
"""
import json
import shutil
import time
from pathlib import Path

from db import DB_PATH, get_db, init_db
import seed
import usage_simulator


BASE = Path(__file__).resolve().parent
RUN_LOG = BASE / "usage_simulator_log.jsonl"
CREATOR_WALLETS = BASE / "demo_creator_wallets.json"
BACKUP_DIR = BASE / "backups"


def _load_events():
    events = []
    if not RUN_LOG.exists():
        raise SystemExit(f"Usage log not found: {RUN_LOG}")
    for line in RUN_LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        events.append(json.loads(line))
    paid = [e for e in events if e.get("event") == "paid_read" and e.get("tx_hash")]
    if not paid:
        raise SystemExit("Usage log has no paid_read events with tx_hash.")
    return events, paid


def _backup_db():
    src = Path(DB_PATH)
    if not src.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dst = BACKUP_DIR / f"obol-{stamp}-before-usage-restore.db"
    shutil.copy2(src, dst)
    return str(dst)


def _restore_creator_wallets(conn):
    if not CREATOR_WALLETS.exists():
        return 0
    wallets = json.loads(CREATOR_WALLETS.read_text(encoding="utf-8"))
    updated = 0
    for item in wallets.values():
        name = item.get("creator_name")
        address = item.get("address")
        if not name or not address:
            continue
        cur = conn.execute(
            "UPDATE creators SET payout_address=? WHERE name=?",
            (address, name),
        )
        updated += cur.rowcount
    conn.commit()
    return updated


def restore():
    events, paid = _load_events()
    backup = _backup_db()

    seed.seed(force=True)
    usage_simulator.enrich_articles(
        target_articles=max(int(e["article_id"]) for e in paid)
    )

    conn = get_db()
    creator_wallet_updates = _restore_creator_wallets(conn)
    creators = {
        r["name"]: r["id"]
        for r in conn.execute("SELECT id, name FROM creators").fetchall()
    }
    inserted = 0
    skipped = 0
    for event in paid:
        tx_hash = event.get("tx_hash")
        if conn.execute("SELECT 1 FROM receipts WHERE tx_hash=?", (tx_hash,)).fetchone():
            skipped += 1
            continue
        creator_id = creators.get(event.get("creator"))
        if not creator_id:
            skipped += 1
            continue
        conn.execute(
            """INSERT INTO receipts(run_id, article_id, creator_id, amount_usdc,
               tx_hash, transaction_id, blockchain, source, buyer, created_at)
               VALUES(NULL,?,?,?,?,?,?,?,?,?)""",
            (
                int(event["article_id"]),
                creator_id,
                float(event.get("amount_usdc") or 0),
                tx_hash,
                event.get("transaction_id", ""),
                "ARC-TESTNET",
                "usage-sim",
                event.get("buyer", ""),
                float(event.get("time") or time.time()),
            ),
        )
        inserted += 1
    conn.commit()

    summary = {
        "creators": conn.execute("SELECT COUNT(*) FROM creators").fetchone()[0],
        "articles": conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0],
        "receipts": conn.execute("SELECT COUNT(*) FROM receipts").fetchone()[0],
        "paid_usdc": round(
            conn.execute("SELECT COALESCE(SUM(amount_usdc),0) FROM receipts").fetchone()[0],
            6,
        ),
    }
    by_creator = [
        dict(r)
        for r in conn.execute(
            """SELECT c.name, ROUND(COALESCE(SUM(r.amount_usdc),0), 6) AS earned_usdc,
                      COUNT(r.id) AS receipts
               FROM creators c LEFT JOIN receipts r ON r.creator_id=c.id
               GROUP BY c.id
               ORDER BY earned_usdc DESC"""
        ).fetchall()
    ]
    conn.close()
    return {
        "backup": backup,
        "events": len(events),
        "inserted_receipts": inserted,
        "skipped_receipts": skipped,
        "creator_wallet_updates": creator_wallet_updates,
        "summary": summary,
        "by_creator": by_creator,
    }


if __name__ == "__main__":
    init_db()
    print(json.dumps(restore(), indent=2, ensure_ascii=False))

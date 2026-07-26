"""
Live testnet usage simulator for Obol.

Creates buyer wallets, enriches creator content, and runs realistic buyer ->
creator paid reads. The goal is not fake organic traction; it is a repeatable
testnet exercise that produces real Circle transaction ids and Arc tx hashes.

Examples:
  python usage_simulator.py --plan
  python usage_simulator.py --create-buyers --buyers 3
  python usage_simulator.py --export-faucet-file
  python usage_simulator.py --live --fund-buyers 0.12 --buyers 20
  python usage_simulator.py --live --purchases 20 --delay-min 3 --delay-max 15
"""
import argparse
import json
import random
import time
from pathlib import Path

from db import init_db, get_db
from circle_service import CircleService
import enrich_demo


BUYERS_FILE = Path(__file__).with_name("demo_buyer_wallets.json")
RUN_LOG = Path(__file__).with_name("usage_simulator_log.jsonl")
DAEMON_STATE = Path(__file__).with_name("usage_daemon_state.json")

TOPICS = [
    ("Agent payment routing", "agents,payments,routing,circle"),
    ("Creator receipts for autonomous readers", "creators,receipts,agents,arc"),
    ("x402 retry flows for machine buyers", "x402,http,payments,agents"),
    ("Arc settlement cost modelling", "arc,fees,settlement,usdc"),
    ("Budget-aware AI research", "research-agents,budgeting,citations"),
    ("Stablecoin revenue dashboards", "stablecoins,revenue,creator-tools"),
    ("Cache reuse and paid content boundaries", "cache,reuse,security,creators"),
    ("Wallet execution for product teams", "circle,wallets,execution,product"),
]

BUYER_PROFILES = [
    "research scout", "protocol analyst", "developer advocate", "market mapper",
    "agent evaluator", "infra reviewer", "payments designer", "creator ops lead",
    "api buyer", "independent validator",
]


def _load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _money(value):
    return round(float(value or 0), 6)


def _log(event):
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with RUN_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"time": time.time(), **event}, ensure_ascii=False) + "\n")


def buyer_wallets():
    return _load_json(BUYERS_FILE, [])


def ensure_buyers(count, live=False):
    wallets = buyer_wallets()
    if len(wallets) >= count:
        return wallets[:count]
    circle = CircleService()
    if live and circle.mode != "live":
        raise SystemExit("Circle live mode is not configured.")
    for idx in range(len(wallets), count):
        label = f"buyer-{idx + 1:03d}-{BUYER_PROFILES[idx % len(BUYER_PROFILES)]}"
        if live:
            w = circle.create_wallet(label=label)
        else:
            w = {
                "id": f"dry_buyer_wallet_{idx + 1:03d}",
                "address": "0x" + f"{idx + 1:040x}"[-40:],
                "blockchain": "ARC-TESTNET",
                "state": "DRY",
            }
        wallets.append({
            "buyer_id": f"buyer-{idx + 1:03d}",
            "persona": BUYER_PROFILES[idx % len(BUYER_PROFILES)],
            "wallet_id": w.get("id"),
            "address": w.get("address"),
            "blockchain": w.get("blockchain"),
            "state": w.get("state"),
            "created_at": time.time(),
            "interest_tags": TOPICS[idx % len(TOPICS)][1],
        })
        _save_json(BUYERS_FILE, wallets)
        _log({"event": "buyer_wallet_created", "buyer": wallets[-1]})
        time.sleep(0.25 if live else 0)
    return wallets[:count]


def export_faucet_file():
    wallets = buyer_wallets()
    out = Path(__file__).with_name("buyer_faucet_addresses.json")
    data = [{"buyer_id": w["buyer_id"], "address": w["address"]} for w in wallets]
    _save_json(out, data)
    return out


def fund_buyers(amount_usdc, buyers_count):
    if amount_usdc <= 0:
        return []
    buyers = ensure_buyers(buyers_count, live=True)
    circle = CircleService()
    if circle.mode != "live":
        raise SystemExit("Live funding requested, but Circle is not configured.")
    funded = []
    for buyer in buyers:
        try:
            tx = circle.send_usdc(
                buyer["address"],
                amount_usdc,
                reference=f"fund-{buyer['buyer_id']}",
            )
            event = {
                "event": "buyer_funded",
                "buyer": buyer["buyer_id"],
                "buyer_wallet_id": buyer["wallet_id"],
                "address": buyer["address"],
                "amount_usdc": _money(amount_usdc),
                "tx_hash": tx.get("tx_hash", ""),
                "transaction_id": tx.get("transaction_id", ""),
            }
        except Exception as exc:
            event = {
                "event": "funding_error",
                "buyer": buyer["buyer_id"],
                "address": buyer["address"],
                "amount_usdc": _money(amount_usdc),
                "error": str(exc)[:500],
            }
        _log(event)
        funded.append(event)
    return funded


def enrich_articles(target_articles=80):
    init_db()
    enrich_demo.enrich()
    conn = get_db()
    creators = [dict(r) for r in conn.execute("SELECT * FROM creators ORDER BY id").fetchall()]
    existing = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    if not creators:
        conn.close()
        raise SystemExit("No creators found. Run seed.py first.")
    now = time.time()
    inserted = 0
    while existing + inserted < target_articles:
        creator = creators[(existing + inserted) % len(creators)]
        topic, tags = TOPICS[(existing + inserted) % len(TOPICS)]
        variant = (existing + inserted) // len(TOPICS) + 1
        title = f"{topic}: field note {variant}"
        row = conn.execute("SELECT 1 FROM articles WHERE title=? AND creator_id=?",
                           (title, creator["id"])).fetchone()
        if row:
            inserted += 1
            continue
        price = round(random.choice([0.006, 0.008, 0.01, 0.012, 0.015, 0.018, 0.024, 0.032, 0.045, 0.06]), 6)
        summary = f"A paid note on {topic.lower()} for autonomous buyers."
        content = (
            f"{creator['name']} publishes this paid note for AI buyers evaluating "
            f"{topic.lower()}. It includes pricing context, implementation caveats, "
            "receipt expectations, and settlement details that help an agent decide "
            "whether the source is worth buying for a specific query."
        )
        conn.execute(
            """INSERT INTO articles(creator_id, title, summary, content, price_usdc, tags, created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (creator["id"], title, summary, content, price, tags, now - inserted * 97),
        )
        inserted += 1
    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    conn.close()
    return {"inserted": inserted, "total_articles": total}


def _score_article(buyer, article):
    tags = set((article.get("tags") or "").lower().split(","))
    interests = set((buyer.get("interest_tags") or "").lower().split(","))
    overlap = len(tags & interests)
    price = float(article["price_usdc"])
    return overlap * 8 + random.random() * 3 - price * 25


def choose_article(conn, buyer):
    articles = [dict(r) for r in conn.execute("""
        SELECT a.*, c.name AS creator_name, c.payout_address
        FROM articles a JOIN creators c ON c.id=a.creator_id
    """).fetchall()]
    # Avoid making every buyer pick the mathematically top item; real usage has taste and noise.
    ranked = sorted(articles, key=lambda a: _score_article(buyer, a), reverse=True)
    window = ranked[:max(5, min(18, len(ranked)))]
    weights = [max(1.0, len(window) - i) for i, _ in enumerate(window)]
    return random.choices(window, weights=weights, k=1)[0]


def receipt_exists(conn, buyer_id, article_id):
    return conn.execute(
        "SELECT 1 FROM receipts WHERE buyer=? AND article_id=?",
        (buyer_id, article_id),
    ).fetchone() is not None


def _buyer_number(buyer):
    try:
        return int(str(buyer.get("buyer_id", "")).split("-")[-1])
    except ValueError:
        return 0


def _parse_buyer_numbers(value):
    if not value:
        return set()
    numbers = set()
    for part in str(value).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            numbers.add(int(part))
        except ValueError:
            if part.startswith("buyer-"):
                numbers.add(int(part.split("-")[-1]))
            else:
                raise
    return numbers


def select_buyers(buyers_count, live=False, buyer_start=1, buyer_end=None,
                  exclude_buyers=None):
    buyers = ensure_buyers(buyers_count, live=live)
    buyer_end = buyer_end or buyers_count
    exclude_buyers = set(exclude_buyers or [])
    selected = [
        buyer for buyer in buyers
        if buyer_start <= _buyer_number(buyer) <= buyer_end
        and _buyer_number(buyer) not in exclude_buyers
    ]
    if not selected:
        raise SystemExit(
            f"No buyers selected. Check --buyer-start {buyer_start}, "
            f"--buyer-end {buyer_end}, --buyers {buyers_count}, "
            f"and excluded buyers {sorted(exclude_buyers)}."
        )
    return selected


def run_purchases(count, buyers_count, live=False, delay_min=0, delay_max=0,
                  buyer_start=1, buyer_end=None, exclude_buyers=None):
    buyers = select_buyers(
        buyers_count,
        live=live,
        buyer_start=buyer_start,
        buyer_end=buyer_end,
        exclude_buyers=exclude_buyers,
    )
    circle = CircleService()
    if live and circle.mode != "live":
        raise SystemExit("Live purchases requested, but Circle is not configured.")
    conn = get_db()
    results = []
    for i in range(count):
        buyer = random.choice(buyers)
        article = choose_article(conn, buyer)
        # Some repeat visits should reuse a prior payment instead of double-paying.
        if receipt_exists(conn, buyer["buyer_id"], article["id"]) and random.random() < 0.8:
            event = {
                "event": "reuse",
                "buyer": buyer["buyer_id"],
                "article_id": article["id"],
                "creator": article["creator_name"],
            }
            _log(event)
            results.append(event)
            continue
        try:
            if live:
                tx = circle.send_usdc_from_wallet(
                    buyer["wallet_id"],
                    article["payout_address"],
                    article["price_usdc"],
                    reference=f"usage-{buyer['buyer_id']}-{article['id']}",
                )
            else:
                tx = {
                    "tx_hash": "0x" + f"{random.getrandbits(256):064x}",
                    "transaction_id": f"dry-{int(time.time()*1000)}-{i}",
                    "blockchain": "ARC-TESTNET",
                    "state": "COMPLETE",
                }
            if tx.get("state") in {"FAILED", "CANCELLED", "DENIED"}:
                raise RuntimeError(f"Circle transaction {tx.get('transaction_id', '')} ended in {tx.get('state')}")
            if live and not tx.get("tx_hash"):
                raise RuntimeError(
                    f"Circle transaction {tx.get('transaction_id', '')} has no Arc txHash yet; not recording paid read"
                )
            conn.execute(
                """INSERT INTO receipts(run_id, article_id, creator_id, amount_usdc,
                   tx_hash, transaction_id, blockchain, source, buyer, created_at)
                   VALUES(NULL,?,?,?,?,?,?,?,?,?)""",
                (
                    article["id"],
                    article["creator_id"],
                    article["price_usdc"],
                    tx.get("tx_hash", ""),
                    tx.get("transaction_id", ""),
                    tx.get("blockchain", "ARC-TESTNET"),
                    "usage-sim",
                    buyer["buyer_id"],
                    time.time(),
                ),
            )
            conn.commit()
            event = {
                "event": "paid_read",
                "live": live,
                "buyer": buyer["buyer_id"],
                "buyer_wallet_id": buyer["wallet_id"],
                "article_id": article["id"],
                "creator": article["creator_name"],
                "amount_usdc": _money(article["price_usdc"]),
                "tx_hash": tx.get("tx_hash", ""),
                "transaction_id": tx.get("transaction_id", ""),
            }
        except Exception as exc:
            event = {
                "event": "error",
                "live": live,
                "buyer": buyer["buyer_id"],
                "article_id": article["id"],
                "creator": article["creator_name"],
                "amount_usdc": _money(article["price_usdc"]),
                "error": str(exc)[:500],
            }
        _log(event)
        results.append(event)
        if delay_max > 0:
            time.sleep(random.uniform(delay_min, delay_max))
    conn.close()
    return results


def _write_daemon_state(state):
    _save_json(DAEMON_STATE, state)


def run_daemon(duration_hours, interval_min, interval_max, max_purchases,
               buyers_count, live=False, buyer_start=1, buyer_end=None,
               exclude_buyers=None):
    if duration_hours <= 0:
        raise SystemExit("--duration-hours must be greater than 0.")
    if interval_min < 0 or interval_max < interval_min:
        raise SystemExit("--interval-max must be >= --interval-min.")
    if live and CircleService().mode != "live":
        raise SystemExit("Live daemon requested, but Circle is not configured.")

    started_at = time.time()
    stop_at = started_at + duration_hours * 3600
    excluded = set(exclude_buyers or [])
    events = []
    paid = 0
    reused = 0
    errors = 0
    loops = 0

    _log({
        "event": "daemon_started",
        "live": live,
        "duration_hours": duration_hours,
        "buyer_start": buyer_start,
        "buyer_end": buyer_end,
        "excluded_buyers": sorted(excluded),
        "max_purchases": max_purchases,
    })

    while time.time() < stop_at and paid < max_purchases:
        loops += 1
        batch = run_purchases(
            1,
            buyers_count,
            live=live,
            buyer_start=buyer_start,
            buyer_end=buyer_end,
            exclude_buyers=excluded,
        )
        event = batch[0] if batch else {"event": "empty"}
        events.append(event)
        if event.get("event") == "paid_read":
            paid += 1
        elif event.get("event") == "reuse":
            reused += 1
        elif event.get("event") == "error":
            errors += 1
            message = str(event.get("error", "")).lower()
            if "insufficient token balance" in message:
                buyer_number = _parse_buyer_numbers(event.get("buyer", ""))
                excluded.update(buyer_number)
                _log({
                    "event": "daemon_buyer_excluded",
                    "buyer": event.get("buyer"),
                    "reason": "insufficient_balance",
                    "excluded_buyers": sorted(excluded),
                })

        state = {
            "running": True,
            "live": live,
            "started_at": started_at,
            "stop_at": stop_at,
            "updated_at": time.time(),
            "loops": loops,
            "paid_reads": paid,
            "reused_reads": reused,
            "errors": errors,
            "excluded_buyers": sorted(excluded),
            "last_event": event,
        }
        _write_daemon_state(state)

        if paid >= max_purchases or time.time() >= stop_at:
            break
        time.sleep(random.uniform(interval_min, interval_max))

    state = {
        "running": False,
        "live": live,
        "started_at": started_at,
        "stop_at": stop_at,
        "finished_at": time.time(),
        "loops": loops,
        "paid_reads": paid,
        "reused_reads": reused,
        "errors": errors,
        "excluded_buyers": sorted(excluded),
        "summary": summarize(),
    }
    _write_daemon_state(state)
    _log({"event": "daemon_finished", **state})
    return state


def reconcile_receipts(limit=100):
    circle = CircleService()
    if circle.mode != "live":
        raise SystemExit("Live reconciliation requested, but Circle is not configured.")
    conn = get_db()
    rows = [dict(r) for r in conn.execute("""
        SELECT id, transaction_id, tx_hash FROM receipts
        WHERE transaction_id IS NOT NULL AND transaction_id <> ''
          AND (tx_hash IS NULL OR tx_hash = '')
        ORDER BY id DESC LIMIT ?
    """, (limit,)).fetchall()]
    results = []
    for row in rows:
        try:
            tx = circle.get_transaction(row["transaction_id"])
            tx_hash = tx.get("txHash", "")
            state = tx.get("state", "")
            if tx_hash:
                conn.execute("UPDATE receipts SET tx_hash=? WHERE id=?", (tx_hash, row["id"]))
                conn.commit()
            event = {
                "event": "receipt_reconciled",
                "receipt_id": row["id"],
                "transaction_id": row["transaction_id"],
                "state": state,
                "tx_hash": tx_hash,
                "updated": bool(tx_hash),
            }
        except Exception as exc:
            event = {
                "event": "reconcile_error",
                "receipt_id": row["id"],
                "transaction_id": row["transaction_id"],
                "error": str(exc)[:500],
            }
        _log(event)
        results.append(event)
    conn.close()
    return results


def summarize():
    conn = get_db()
    rows = [dict(r) for r in conn.execute("""
        SELECT c.name,
               ROUND(COALESCE(SUM(r.amount_usdc), 0), 4) AS earned_usdc,
               COUNT(r.id) AS receipts,
               COUNT(DISTINCT r.buyer) AS buyers,
               SUM(CASE WHEN r.transaction_id IS NOT NULL AND r.transaction_id <> '' THEN 1 ELSE 0 END) AS circle_receipts
        FROM creators c LEFT JOIN receipts r ON r.creator_id=c.id
        GROUP BY c.id ORDER BY earned_usdc DESC
    """).fetchall()]
    conn.close()
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--create-buyers", action="store_true")
    parser.add_argument("--buyers", type=int, default=100)
    parser.add_argument("--articles", type=int, default=80)
    parser.add_argument("--purchases", type=int, default=100)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--fund-buyers", type=float, default=0,
                        help="Send this much testnet USDC from the agent wallet to each buyer wallet.")
    parser.add_argument("--export-faucet-file", action="store_true")
    parser.add_argument("--reconcile", action="store_true",
                        help="Fetch missing tx hashes for stored Circle transaction ids.")
    parser.add_argument("--delay-min", type=float, default=0)
    parser.add_argument("--delay-max", type=float, default=0)
    parser.add_argument("--buyer-start", type=int, default=1,
                        help="First buyer number eligible for purchases, e.g. 1 for buyer-001.")
    parser.add_argument("--buyer-end", type=int, default=None,
                        help="Last buyer number eligible for purchases, e.g. 30 for buyer-030.")
    parser.add_argument("--exclude-buyers", default="",
                        help="Comma-separated buyer numbers to skip, e.g. 21,buyer-009.")
    parser.add_argument("--duration-hours", type=float, default=0,
                        help="Run a slow background usage loop for this many hours.")
    parser.add_argument("--interval-min", type=float, default=180,
                        help="Minimum seconds between daemon purchases.")
    parser.add_argument("--interval-max", type=float, default=420,
                        help="Maximum seconds between daemon purchases.")
    parser.add_argument("--max-daemon-purchases", type=int, default=140,
                        help="Safety cap for paid reads in daemon mode.")
    args = parser.parse_args()
    exclude_buyers = _parse_buyer_numbers(args.exclude_buyers)

    init_db()
    article_result = enrich_articles(args.articles)
    output = {"articles": article_result, "buyers_existing": len(buyer_wallets())}

    if args.create_buyers:
        output["buyers"] = ensure_buyers(args.buyers, live=args.live)
    if args.export_faucet_file:
        output["faucet_file"] = str(export_faucet_file())
    if args.fund_buyers:
        output["funding"] = fund_buyers(args.fund_buyers, args.buyers)
    if args.duration_hours and not args.plan:
        output["daemon"] = run_daemon(
            args.duration_hours,
            args.interval_min,
            args.interval_max,
            args.max_daemon_purchases,
            args.buyers,
            live=args.live,
            buyer_start=args.buyer_start,
            buyer_end=args.buyer_end,
            exclude_buyers=exclude_buyers,
        )
    elif not args.plan and args.purchases:
        output["purchases"] = run_purchases(
            args.purchases, args.buyers, live=args.live,
            delay_min=args.delay_min, delay_max=args.delay_max,
            buyer_start=args.buyer_start, buyer_end=args.buyer_end,
            exclude_buyers=exclude_buyers,
        )
    if args.reconcile:
        output["reconcile"] = reconcile_receipts()
    output["summary"] = summarize()
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""
x402 — HTTP-native pay-per-read for articles.

Any agent (not just ours) can fetch a creator's article through the standard
"402 Payment Required → pay → retry with proof" flow:

  GET /x402/articles/<id>                       -> 402 + a payment challenge
  GET /x402/articles/<id>   X-Payment: <txhash>  -> 200 + the full content

This is Obol's public machine-payable surface: other builders can point their
agents at it and complete an HTTP 402 challenge-and-retry flow.
"""
import time
import uuid
import hashlib

from db import get_db

ASSET = "USDC"
NETWORK = "arc-testnet"


def build_challenge(article):
    """Return the x402 challenge body for an unpaid request."""
    return {
        "error": "payment required",
        "x402Version": 1,
        "accepts": [{
            "scheme": "exact",
            "network": NETWORK,
            "asset": ASSET,
            "amount": f"{article['price_usdc']:.6f}",
            "payTo": article["payout_address"],
            "resource": f"article:{article['id']}",
            "description": article["title"],
            "nonce": uuid.uuid4().hex,
        }],
    }


def valid_proof(proof):
    """Mock verification: a tx hash shaped like 0x… is accepted.
    (Live mode could verify the transfer on-chain via Circle.)"""
    return isinstance(proof, str) and proof.startswith("0x") and len(proof) >= 10


def grant(article, buyer, tx_hash, source="x402", transaction_id="",
          settlement_mode="mock"):
    """Record an external purchase receipt and return it.

    The mock proof is a tx hash, so treat it as an idempotency key. Replaying the
    same proof for the same resource returns the original receipt; replaying it
    against a different article is rejected to preserve resource binding.
    """
    conn = get_db()
    cur = conn.cursor()
    existing = cur.execute("SELECT * FROM receipts WHERE tx_hash=? AND source=?",
                           (tx_hash, source)).fetchone()
    if existing:
        receipt = dict(existing)
        conn.close()
        if receipt["article_id"] != article["id"]:
            raise ValueError("payment proof already used for another resource")
        return receipt
    cur.execute("""INSERT INTO receipts(run_id, article_id, creator_id, amount_usdc,
                   tx_hash, transaction_id, blockchain, settlement_mode,
                   source, buyer, created_at)
                   VALUES(NULL,?,?,?,?,?,?,?,?,?,?)""",
                (article["id"], article["creator_id"], article["price_usdc"],
                 tx_hash, transaction_id, "ARC-TESTNET", settlement_mode,
                 source, buyer, time.time()))
    conn.commit()
    rid = cur.lastrowid
    receipt = dict(cur.execute("SELECT * FROM receipts WHERE id=?", (rid,)).fetchone())
    conn.close()
    return receipt


def demo_grant(article, buyer, tx_hash):
    """Return a clearly simulated, non-persistent receipt for public demos.

    A format-shaped proof is useful for demonstrating the x402 retry flow, but
    it must never inflate the formal payment ledger or be presented as an
    on-chain Arc transfer.
    """
    digest = hashlib.sha256(
        f"{article['id']}:{buyer}:{tx_hash}".encode("utf-8")
    ).hexdigest()[:16]
    return {
        "id": f"demo-{digest}",
        "run_id": None,
        "article_id": article["id"],
        "creator_id": article["creator_id"],
        "amount_usdc": article["price_usdc"],
        "tx_hash": tx_hash,
        "transaction_id": "",
        "blockchain": "SIMULATED-ARC-TESTNET",
        "settlement_mode": "mock",
        "source": "x402-demo",
        "buyer": buyer,
        "created_at": time.time(),
        "persisted": False,
    }

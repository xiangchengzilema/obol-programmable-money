"""
Try demo persona queries against the live/local API.

This intentionally creates real local agent runs and may create live payments
when settlement is configured. Use only when the wallet has testnet USDC.
"""
import json
import urllib.request


API = "http://localhost:5001"

QUERIES = [
    ("creator economist", "creator pricing benchmarks AI readers per-read revenue", 0.020),
    ("publisher", "publisher paywalls AI readers locked previews receipts", 0.020),
    ("budget researcher", "agent audit logs cache boundaries replay protection", 0.016),
    ("api builder", "x402 endpoints HTTP agents pay tools content", 0.016),
    ("proof designer", "human readable txhash proof machine payments", 0.016),
]


def post(path, body):
    req = urllib.request.Request(
        API + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def main():
    for name, query, budget in QUERIES:
        run = post("/api/agent/run", {"query": query, "budget_usdc": budget})
        decisions = run["decisions"]
        counts = {k: len([d for d in decisions if d["decision"] == k])
                  for k in ("buy", "reuse", "skip")}
        print(json.dumps({
            "persona": name,
            "spent": run["total_spent"],
            "saved": run["saved_usdc"],
            "coverage": run["coverage"],
            "receipts": len(run["receipts"]),
            "decisions": counts,
            "first_receipt": run["receipts"][0]["tx_hash"] if run["receipts"] else "",
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()

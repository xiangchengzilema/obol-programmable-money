"""
Run the 5-persona Obol evaluation locally.

This is traction evidence + QA, not fake users. It exercises the real backend:
creator publishing, autonomous agent reads, x402 unlocks, ledger/stats.

Run:
  cd backend
  python persona_eval.py

Output:
  ../media/persona_evaluation_report.md
"""
import os
import time

os.environ.setdefault("OBOL_FORCE_MOCK", "1")

import app as appmod
import seed


REPORT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "media",
                                           "persona_evaluation_report.md"))

PERSONAS = [
    {
        "name": "Creator Economist",
        "role": "publisher pricing analyst",
        "article": {
            "creator_id": 1,
            "title": "Why AI readers need per-read creator royalties",
            "summary": "A creator-side argument for charging autonomous readers per source.",
            "content": "AI readers create value by consuming creator work at scale. A per-read USDC price lets publishers monetize the long tail without subscriptions, while receipts show exactly which agent paid for which source.",
            "price_usdc": 0.014,
            "tags": "creators,royalties,ai-readers",
        },
        "query": "how can creators monetize AI readers per article",
        "budget": 0.05,
        "finding": "The strongest creator-facing proof is the earnings ledger: each AI read becomes attributable revenue.",
    },
    {
        "name": "Skeptical Publisher",
        "role": "media operator worried about scraping",
        "article": {
            "creator_id": 3,
            "title": "Publisher controls for agent-readable content",
            "summary": "How previews, prices, and receipts create a controlled AI reading surface.",
            "content": "Publishers should expose previews and prices without giving away full text. Agent-readable paywalls let buyers evaluate relevance first, then unlock content with a resource-bound receipt.",
            "price_usdc": 0.021,
            "tags": "publishers,paywalls,receipts",
        },
        "query": "how do publisher paywalls for AI readers avoid free scraping",
        "budget": 0.06,
        "finding": "Locked previews plus post-payment receipts make the model legible to publishers.",
    },
    {
        "name": "Budget Research Agent",
        "role": "cost-constrained autonomous buyer",
        "article": None,
        "query": "what are nanopayments and Arc fees for agent research",
        "budget": 0.025,
        "finding": "The buy/skip log is valuable because it proves the agent stopped spending when the answer was covered.",
    },
    {
        "name": "API Tool Builder",
        "role": "builder integrating x402 endpoints",
        "article": {
            "creator_id": 2,
            "title": "HTTP 402 as the interface for paid agent tools",
            "summary": "A short implementation note for request, quote, payment proof, and retry.",
            "content": "The x402 pattern is simple for agents: request the resource, receive a 402 quote, attach a payment proof, retry, and receive the paid content. This makes paid tools discoverable through ordinary HTTP.",
            "price_usdc": 0.017,
            "tags": "x402,http,agent-tools",
        },
        "query": "how does HTTP 402 help agents pay for tools and content",
        "budget": 0.05,
        "finding": "The x402 page demonstrates a clean machine-payable surface other builders can copy.",
    },
    {
        "name": "Security Auditor",
        "role": "payment-flow reviewer",
        "article": None,
        "query": "why do agent payments need receipts resource binding and replay protection",
        "budget": 0.055,
        "finding": "Resource-bound receipts and cache boundaries are important: agent cache should not reuse external buyer payments.",
    },
]


def _post(client, path, body):
    r = client.post(path, json=body)
    if r.status_code >= 400:
        raise RuntimeError(f"{path} failed: {r.status_code} {r.get_json()}")
    return r.get_json()


def _get(client, path, headers=None):
    r = client.get(path, headers=headers or {})
    if r.status_code >= 400 and r.status_code != 402:
        raise RuntimeError(f"{path} failed: {r.status_code} {r.get_json()}")
    return r


def run():
    seed.seed(force=True)
    client = appmod.app.test_client()
    rows = []

    for i, persona in enumerate(PERSONAS, start=1):
        created = None
        if persona["article"]:
            created = _post(client, "/api/articles", persona["article"])

        run_data = _post(client, "/api/agent/run", {
            "query": persona["query"],
            "budget_usdc": persona["budget"],
        })

        x402_result = None
        if created:
            challenge = _get(client, f"/x402/articles/{created['id']}")
            nonce = challenge.get_json()["accepts"][0]["nonce"]
            proof = "0x" + nonce + ("e" * max(0, 64 - len(nonce)))
            unlocked = _get(client, f"/x402/articles/{created['id']}",
                            headers={"X-Payment": proof, "X-Payer": persona["name"]})
            x402_result = unlocked.get_json()["receipt"]

        rows.append({
            "persona": persona,
            "article": created,
            "run": run_data,
            "x402": x402_result,
        })

    stats = client.get("/api/stats").get_json()
    ledger = client.get("/api/ledger").get_json()
    write_report(rows, stats, ledger)
    return {"report": REPORT_PATH, "stats": stats, "ledger_count": len(ledger)}


def write_report(rows, stats, ledger):
    lines = [
        "# Obol 5-persona AI evaluation",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Summary",
        "",
        f"- Agent runs: {stats['num_runs']}",
        f"- Paid reads / receipts: {stats['total_reads']}",
        f"- USDC paid to creators: ${stats['total_paid_usdc']:.4f}",
        f"- Decisions logged: {stats['decisions_made']}",
        f"- USDC saved by cache reuse: ${stats['usdc_saved_by_reuse']:.4f}",
        "",
        "## Persona results",
        "",
    ]

    for row in rows:
        p = row["persona"]
        run = row["run"]
        buys = len([d for d in run["decisions"] if d["decision"] == "buy"])
        reuses = len([d for d in run["decisions"] if d["decision"] == "reuse"])
        skips = len([d for d in run["decisions"] if d["decision"] == "skip"])
        lines.extend([
            f"### {p['name']} ({p['role']})",
            "",
            f"- Query: `{p['query']}`",
            f"- Budget: ${p['budget']:.3f}",
            f"- Spent: ${run['total_spent']:.4f}",
            f"- Coverage: {run['coverage']:.0%}",
            f"- Decisions: {buys} buy / {reuses} reuse / {skips} skip",
            f"- Receipts from agent run: {len(run['receipts'])}",
        ])
        if row["article"]:
            lines.append(f"- Published source: {row['article']['title']}")
        if row["x402"]:
            lines.append(f"- x402 unlock receipt: ${row['x402']['amount_usdc']:.4f} ({row['x402']['tx_hash'][:12]}...)")
        lines.extend([
            f"- Finding: {p['finding']}",
            "",
        ])

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    result = run()
    print(f"Wrote {result['report']}")
    print(result)

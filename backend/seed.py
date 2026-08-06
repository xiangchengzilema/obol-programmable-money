"""
Seed demo creators and articles so the marketplace and agent demo have useful
content out of the box. Run: python seed.py  (use --force to wipe and reseed).
"""
import sys
import time

from db import init_db, get_db


CREATORS = [
    ("Alice Chen", "0x1111111111111111111111111111111111111111"),
    ("DeFi Daily", "0x2222222222222222222222222222222222222222"),
    ("Maya Okonkwo", "0x3333333333333333333333333333333333333333"),
    ("The Arc Letter", "0x4444444444444444444444444444444444444444"),
    ("Token Terminal Notes", "0x5555555555555555555555555555555555555555"),
    ("StableLab Research", "0x6666666666666666666666666666666666666666"),
    ("AgentOps Weekly", "0x7777777777777777777777777777777777777777"),
    ("Rina Park", "0x8888888888888888888888888888888888888888"),
    ("Northstar Protocols", "0x9999999999999999999999999999999999999999"),
]


# Keep the original first six articles in the same order so tests and demo
# scripts that reference article ids stay stable after a force reset.
ARTICLES = [
    (0, "How Circle Gateway unifies USDC liquidity",
     "Gateway lets apps treat USDC across chains as one balance.",
     "Circle Gateway abstracts cross-chain USDC into a single unified balance. "
     "Instead of bridging, apps draw from one liquidity layer; settlement happens "
     "on the destination chain. For agents this means a wallet that just works "
     "everywhere, paying out of one balance. On Arc, fees are predictable USDC.",
     0.020, "usdc,gateway,circle,liquidity"),
    (1, "Nanopayments: pricing per-call agent services",
     "Why x402 per-call beats subscriptions for agent APIs.",
     "Subscriptions force buyers to pre-commit. Nanopayments charge per call: "
     "$0.001 per summary, $0.01 per image. Agents pay only for what they use, and "
     "providers monetize the long tail of tiny requests. x402 returns a 402 with a "
     "price; the caller pays in USDC and retries. Sub-second settlement on Arc makes "
     "this practical.",
     0.015, "nanopayments,x402,agents,pricing"),
    (2, "Reputation systems for agent-to-agent payments",
     "How agents decide which other agents to trust and pay.",
     "When agents pay agents, discovery needs reputation. ERC-8004 style records let "
     "an agent check a counterparty history before paying. Combine on-chain receipts "
     "with a scoring layer and agents can route work to reliable providers and avoid "
     "rug-style services.",
     0.025, "reputation,agents,erc-8004,trust"),
    (3, "Arc testnet: predictable fees for high-frequency payments",
     "Sub-second finality and ~$0.01 USDC fees change what is economical.",
     "Volatile gas kills micro-payments. Arc settles in USDC with predictable fees and "
     "sub-second deterministic finality, so paying $0.002 to read an article nets out "
     "positive. This is the substrate that makes per-article and per-second payments real.",
     0.010, "arc,testnet,fees,settlement"),
    (0, "Streaming pay-per-second for compute",
     "Approve a rate, not each transaction; tap to stop.",
     "Streaming payments authorize a rate, for example $0.0001 per second of GPU, "
     "rather than signing each transaction. A meter accrues and settles continuously; "
     "the payer can pause or stop instantly. Useful for GPU rental, live data feeds, "
     "and transcription.",
     0.030, "streaming,compute,pay-per-second"),
    (1, "A gentle intro to prediction markets",
     "What they are and why settlement is the hard part.",
     "Prediction markets price the probability of future events. The hard problem is "
     "settlement: determining truth without trusting a single operator. Verifiable "
     "claim resolution is where most designs live or die.",
     0.012, "prediction-markets,settlement,defi"),
    (4, "Creator pricing benchmarks for AI readers",
     "Observed price bands for summaries, research notes, and analyst memos.",
     "AI readers do not need a full subscription to every creator. They need precise "
     "access to the one source that answers the query. Creator pricing works best "
     "when the preview is free, the full text is locked, and the per-read price sits "
     "between $0.004 and $0.030 depending on depth.",
     0.018, "creators,pricing,benchmarks,ai-readers"),
    (5, "Stablecoin settlement UX for autonomous apps",
     "How product teams should expose live stablecoin settlement without overwhelming users.",
     "Autonomous apps need receipts, status, and recovery paths. Users do not need "
     "wallet internals on every screen; they need amount, counterparty, chain, and "
     "transaction hash. The best interfaces make settlement observable but not noisy.",
     0.022, "stablecoins,ux,circle,receipts"),
    (6, "Agent audit logs that buyers can actually read",
     "A practical schema for explaining why an agent spent money.",
     "A useful agent log should show intent, candidate source, price, decision, and "
     "reason. It should also separate external unlock receipts from the agent own "
     "cache. Otherwise a malicious buyer could use somebody else's payment as free access.",
     0.014, "agents,audit-logs,cache,security"),
    (7, "How independent agents should buy research",
     "Budgeting and source selection patterns for autonomous research agents.",
     "The strongest research agents do not buy every source. They rank by expected "
     "coverage per dollar, skip redundant articles, and stop when enough evidence is "
     "collected. The receipt is not just payment proof; it is part of the citation trail.",
     0.019, "research-agents,budgeting,citations"),
    (8, "Arc fee predictability and creator payouts",
     "Why predictable USDC costs matter for creator monetization.",
     "If fees spike unpredictably, one-cent content is impossible. Arc's USDC-denominated "
     "fee model lets a creator price a source without guessing the network cost. That "
     "turns small creator payouts from a spreadsheet idea into an interface primitive.",
     0.011, "arc,fees,creators,usdc"),
    (4, "What a receipt should prove in agent commerce",
     "Minimum receipt fields for agent-to-creator payments.",
     "A receipt should prove who paid, who earned, what resource was accessed, how much "
     "moved, which chain settled it, and which transaction hash can be checked later. "
     "Without resource binding, receipts are easy to replay or misinterpret.",
     0.016, "receipts,agent-commerce,resource-binding"),
    (5, "Circle wallet operations for product teams",
     "A product-level view of wallet execution, keys, and transaction status.",
     "Circle wallets let the product request execution without holding private keys in "
     "the application code. For demos, the important proof is not a hidden key ceremony; "
     "it is the transaction id, state, amount, and chain hash after broadcast.",
     0.020, "circle,wallets,execution,product"),
    (6, "Designing x402 endpoints for AI buyers",
     "How to make HTTP-native payments understandable to agents.",
     "An x402 endpoint should make the price, asset, pay-to address, nonce, and resource "
     "clear before payment. After payment, it should return the content and a receipt. "
     "Agents need deterministic failure modes, not vague checkout pages.",
     0.013, "x402,http,agents,payments"),
    (7, "Publisher objections to AI paywalls",
     "What skeptical media teams ask before allowing autonomous readers.",
     "Publishers ask whether agents can scrape previews, whether receipts bind to a "
     "specific article, whether repeat reads double-charge, and whether revenue is visible "
     "without waiting for monthly settlement. A good system answers those before sales.",
     0.017, "publishers,paywalls,ai-readers,revenue"),
    (8, "The case for tiny paid data feeds",
     "From static articles to priced live feeds for agents.",
     "Per-read articles are the first step. The same rail can price live market notes, "
     "weather updates, compliance snippets, and model evaluation traces. Agents become "
     "economic users of the web instead of anonymous scrapers.",
     0.024, "data-feeds,agents,nanopayments"),
    (4, "Cache reuse without cheating creators",
     "When repeat reads should be free and when they should not.",
     "A buyer own cached receipt can justify a free repeat read. Another buyer x402 "
     "receipt should not. Clear cache boundaries protect creators while preventing the "
     "same agent from paying twice for the same source.",
     0.012, "cache,reuse,creators,security"),
    (5, "Revenue console metrics for creator tools",
     "The few numbers that make paid AI reads legible.",
     "A creator dashboard should show paid reads, total USDC earned, latest payer type, "
     "article-level revenue, and receipt hashes. Too many charts hide the money movement; "
     "too few make the product feel unverifiable.",
     0.015, "creator-tools,metrics,revenue"),
    (6, "Validator markets and paid evidence",
     "How dispute systems and paid sources can share receipt primitives.",
     "Agent commerce, validator work, and creator paywalls all need the same primitive: "
     "a resource-bound payment receipt. Whether the work is a research answer or a model "
     "evaluation, the buyer needs proof that money moved for a specific deliverable.",
     0.028, "validators,evidence,receipts,agents"),
    (7, "Human-readable proofs for machine payments",
     "Why transaction proof still needs product design.",
     "A txHash alone is not a product. Users need the chain, amount, counterparty, and "
     "resource next to it. The interface should make the proof obvious enough that a "
     "judge can understand it in ten seconds.",
     0.014, "design,proof,txhash,fintech"),
    (8, "Autonomous subscriptions versus pay-per-read",
     "Where subscriptions fail for agent buyers.",
     "Subscriptions assume a stable human relationship. Agents often need one source, "
     "one time, for one query. Pay-per-read makes the economic action match the actual "
     "work: access a resource, pay the creator, store the receipt.",
     0.018, "subscriptions,pay-per-read,agents"),
]


def seed(force=False):
    init_db()
    conn = get_db()
    cur = conn.cursor()
    if force:
        for t in (
            "payment_claims", "receipts", "decisions", "agent_runs",
            "articles", "creators",
        ):
            cur.execute(f"DELETE FROM {t}")
        try:
            cur.execute("DELETE FROM sqlite_sequence WHERE name IN "
                        "('payment_claims','receipts','decisions','agent_runs',"
                        "'articles','creators')")
        except Exception:
            pass
    if cur.execute("SELECT COUNT(*) FROM creators").fetchone()[0] > 0 and not force:
        print("Already seeded (use --force to reset).")
        conn.close()
        return
    cids = []
    now = time.time()
    for offset, (name, addr) in enumerate(CREATORS):
        cur.execute("INSERT INTO creators(name, payout_address, created_at) VALUES(?,?,?)",
                    (name, addr, now - (len(CREATORS) - offset) * 3600))
        cids.append(cur.lastrowid)
    for offset, (ci, title, summary, content, price, tags) in enumerate(ARTICLES):
        cur.execute("""INSERT INTO articles(creator_id, title, summary, content, price_usdc, tags, created_at)
                       VALUES(?,?,?,?,?,?,?)""",
                    (cids[ci], title, summary, content, price, tags,
                     now - (len(ARTICLES) - offset) * 1800))
    conn.commit()
    conn.close()
    print(f"Seeded {len(CREATORS)} creators, {len(ARTICLES)} articles.")


if __name__ == "__main__":
    seed(force="--force" in sys.argv)

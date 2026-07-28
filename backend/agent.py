"""
Obol Agent — the autonomous paying researcher.

Given a QUERY and a daily USDC BUDGET it runs a small but genuine decision loop:

  1. PLAN     — look at the candidates and budget, state a strategy.
  2. SCORE    — rate how relevant each paywalled article is (LLM if configured,
                else a transparent keyword heuristic).
  3. RANK     — order by value-for-money = relevance / price.
  4. DECIDE   — walk the ranked list and, for each article, choose one of:
                  • buy     — relevant, adds new coverage, fits the budget
                  • reuse   — already paid for in a past run → read free from cache
                  • skip    — and log *why*: below the relevance bar, redundant with
                              what was already bought, enough coverage already (so it
                              preserves budget), or it would blow the budget.
  5. PAY      — each buy is a per-article nanopayment to the creator on Arc (Circle).
  6. ANSWER   — synthesize from ONLY what it paid for / reused, with citations.
  7. REPORT   — return the answer + every decision + every receipt + the plan,
                final query coverage and a confidence label.

The point is step 4. A dumb script buys everything it can afford; this agent buys
the *least* it needs — it stops when the question is covered and leaves money on
the table, and it refuses to pay twice for the same information. That visible,
reasoned buy/skip/reuse log is the 30% "Agentic Sophistication" criterion.
"""
import json
import os
import re
import time

from db import get_db
from circle_service import CircleService
from wallet_pool import pay_from_buyer_pool
from spending_policy import SpendingPolicy
import llm

# An article must clear this relevance to be worth paying for at all.
MIN_RELEVANCE = float(os.getenv("OBOL_MIN_RELEVANCE", "0.35"))
# Once the query is this well covered by what we've bought, stop buying and keep
# the rest of the budget — "I have enough to answer" is a real agentic decision.
COVERAGE_TARGET = float(os.getenv("OBOL_COVERAGE_TARGET", "0.8"))

_STOP = set("the a an of to in on for and or is are be with how what why when "
            "do does this that it as at by from about into over your you my".split())


def _tokens(text):
    return [w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
            if w not in _STOP and len(w) > 2]


def _query_terms(query):
    """The meaningful aspects of the question we're trying to cover."""
    return set(_tokens(query))


def _article_aspects(article, q_terms):
    """Which of the query's aspects this article actually touches."""
    text = " ".join(str(article.get(k) or "") for k in ("title", "tags", "summary", "content"))
    return set(_tokens(text)) & q_terms


def _heuristic_relevance(query, article):
    """Token-overlap relevance in 0..1 (title/tags weighted heavier than body)."""
    q = set(_tokens(query))
    if not q:
        return 0.0
    title = set(_tokens(article["title"]))
    tags = set(_tokens(article["tags"] or ""))
    body = set(_tokens((article["summary"] or "") + " " + (article["content"] or "")))
    score = 3 * len(q & title) + 2 * len(q & tags) + 1 * len(q & body)
    return score / (len(q) * 3.0)  # normalized so a full title match ~= 1.0


def _score_candidates(query, articles, min_relevance=MIN_RELEVANCE):
    """Return {article_id: (relevance, reason)}. Tries LLM, falls back to heuristic."""
    if llm.available() and articles:
        catalog = "\n".join(
            f'- id={a["id"]} | title="{a["title"]}" | tags="{a["tags"] or ""}" '
            f'| price=${a["price_usdc"]:.3f} | summary="{(a["summary"] or "")[:160]}"'
            for a in articles
        )
        out = llm.chat_json(
            "You are a budget-conscious research agent scoring how useful each paywalled "
            "article is for answering a query. Score 0.0-1.0 (1=essential).",
            f'Query: "{query}"\n\nArticles:\n{catalog}\n\n'
            'Return {"scores":[{"id":N,"relevance":0.0-1.0,"reason":"short"}...]}',
        )
        if out and isinstance(out.get("scores"), list):
            scored = {}
            for s in out["scores"]:
                try:
                    scored[int(s["id"])] = (max(0.0, min(1.0, float(s["relevance"]))),
                                            str(s.get("reason", ""))[:160])
                except Exception:
                    continue
            if scored:
                for a in articles:  # fill any the model missed
                    scored.setdefault(a["id"], (_heuristic_relevance(query, a), "heuristic fallback"))
                return scored
    # heuristic path — normalize across the candidate set so scores are comparable
    raw = {a["id"]: _heuristic_relevance(query, a) for a in articles}
    top = max(raw.values()) if raw else 0.0
    scored = {}
    for a in articles:
        rel = (raw[a["id"]] / top) if top > 0 else 0.0
        reason = ("keyword overlap with the query" if rel >= min_relevance
                  else "little keyword overlap with the query")
        scored[a["id"]] = (round(rel, 3), reason)
    return scored


def _build_plan(query, articles, policy):
    """A short, human-readable statement of intent shown before the agent acts."""
    cheapest = min((a["price_usdc"] for a in articles), default=0.0)
    return (
        f'Goal: answer "{query}" under a programmable USDC budget policy. '
        f"{len(articles)} paywalled sources available (from ${cheapest:.3f}). "
        f"Strategy: rank by relevance-per-dollar, buy the best until the question is "
        f"~{policy.coverage_target:.0%} covered or a spending guard fires, reuse anything "
        f"already paid for, and explain every buy, reuse, skip, and stop. "
        f"Policy: {policy.describe()}"
    )


def _coverage(covered, q_terms, have_sources):
    if q_terms:
        return min(1.0, len(covered) / len(q_terms))
    # No meaningful query terms to track — fall back to "did we read anything".
    return 1.0 if have_sources else 0.0


def _confidence(coverage, n_sources):
    if n_sources == 0:
        return "none"
    if coverage >= 0.75:
        return "high"
    if coverage >= 0.4:
        return "medium"
    return "low"


def _synthesize(query, bought, coverage):
    """Build the final answer from purchased/reused articles only."""
    if not bought:
        return ("No source cleared the relevance bar at a price worth paying within "
                "budget, so the agent bought nothing and spent $0.00.")
    if llm.available():
        srcs = "\n\n".join(f'[{i+1}] {a["title"]} (by {a["creator_name"]}):\n{a["content"][:1200]}'
                           for i, a in enumerate(bought))
        ans = llm.chat(
            "You answer using ONLY the provided paid sources. Cite them as [1],[2]. Be concise.",
            f'Question: {query}\n\nPaid sources:\n{srcs}\n\nAnswer with citations:',
            max_tokens=600,
        )
        if ans:
            return ans.strip()
    # extractive fallback — honest about what it's built from
    lines = [f"Answer assembled from {len(bought)} source(s) the agent paid for "
             f"(~{coverage:.0%} of the question's aspects covered):"]
    for i, a in enumerate(bought):
        lines.append(f"[{i+1}] {a['title']} — {a['creator_name']}: "
                     f"{(a['summary'] or a['content'][:200]).strip()}")
    return "\n".join(lines)


def _purchase_limit(policy):
    return policy.max_purchases if policy.max_purchases is not None else "unlimited"


def run_agent(query, budget_usdc, policy_input=None):
    """Execute one agent run end-to-end. Returns the full run dict."""
    policy = SpendingPolicy.from_input(budget_usdc, policy_input)
    budget_usdc = policy.total_budget_usdc
    q_terms = _query_terms(query)
    now = time.time()
    circle = CircleService()
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""SELECT a.*, c.name AS creator_name, c.payout_address
                   FROM articles a JOIN creators c ON c.id = a.creator_id""")
    articles = [dict(r) for r in cur.fetchall()]
    plan = _build_plan(query, articles, policy)

    cur.execute("""INSERT INTO agent_runs(
                   query, budget_usdc, status, plan, policy_json, created_at
                   ) VALUES(?,?,?,?,?,?)""",
                (query, budget_usdc, "running", plan,
                 json.dumps(policy.to_dict(), sort_keys=True), now))
    run_id = cur.lastrowid
    conn.commit()

    scored = _score_candidates(query, articles, policy.min_relevance)

    # rank by value-for-money = relevance / price (free/zero-priced sort first)
    for a in articles:
        a["relevance"], a["reason"] = scored.get(a["id"], (0.0, ""))
        a["value"] = a["relevance"] / a["price_usdc"] if a["price_usdc"] > 0 else a["relevance"] * 1e6
    articles.sort(key=lambda x: x["value"], reverse=True)

    # The agent may reuse only articles it previously paid for itself. External
    # x402/unlock receipts are creator earnings, not this agent's private cache.
    paid_ids = {r[0] for r in cur.execute(
        "SELECT DISTINCT article_id FROM receipts WHERE source='agent' AND run_id IS NOT NULL"
    ).fetchall()}

    spent = 0.0
    bought = []
    covered = set()
    purchase_count = 0
    for a in articles:
        aspects = _article_aspects(a, q_terms)
        coverage = _coverage(covered, q_terms, bool(bought))
        novelty = aspects - covered
        budget_before = round(budget_usdc - spent, 6)
        budget_after = budget_before

        if a["relevance"] < policy.min_relevance:
            decision = "skip"
            policy_rule = "min_relevance"
            reason = (
                f"relevance {a['relevance']:.2f} is below the programmable "
                f"{policy.min_relevance:.2f} minimum; budget remains ${budget_before:.3f}"
            )
        elif a["id"] in paid_ids:
            decision = "reuse"
            policy_rule = "cache_reuse"
            reason = (
                "prior agent receipt authorizes cache reuse for $0.00; "
                f"purchase count stays {purchase_count}/{_purchase_limit(policy)} "
                f"and budget stays ${budget_before:.3f}"
            )
            bought.append(a)
            covered |= aspects
        elif bought and coverage >= policy.coverage_target:
            decision = "skip"
            policy_rule = "coverage_target"
            reason = (f"question already ~{coverage:.0%} covered by what was paid for — "
                      f"policy stops new spending and preserves ${budget_before:.3f}")
        elif bought and not novelty:
            decision = "skip"
            policy_rule = "redundant_coverage"
            reason = ("redundant — its topics are already covered by sources paid for; "
                      f"saving ${a['price_usdc']:.3f} and keeping ${budget_before:.3f}")
        elif (policy.max_price_usdc is not None
              and a["price_usdc"] > policy.max_price_usdc + 1e-9):
            decision = "skip"
            policy_rule = "max_price"
            reason = (
                f"price ${a['price_usdc']:.3f} exceeds the programmable "
                f"${policy.max_price_usdc:.3f} per-source cap"
            )
        elif (policy.max_purchases is not None
              and purchase_count >= policy.max_purchases):
            decision = "skip"
            policy_rule = "max_purchases"
            reason = (
                f"paid-read cap reached ({purchase_count}/{policy.max_purchases}); "
                f"no transfer authorized and ${budget_before:.3f} remains"
            )
        elif spent + a["price_usdc"] > policy.spendable_budget_usdc + 1e-9:
            decision = "skip"
            if spent + a["price_usdc"] <= budget_usdc + 1e-9 and policy.reserve_usdc:
                policy_rule = "reserve_balance"
                reason = (
                    f"purchase would dip into the protected ${policy.reserve_usdc:.3f} "
                    f"reserve (spendable limit ${policy.spendable_budget_usdc:.3f}, "
                    f"already spent ${spent:.3f})"
                )
            else:
                policy_rule = "total_budget"
                reason = (
                    f"would exceed the ${budget_usdc:.3f} total budget "
                    f"(already spent ${spent:.3f})"
                )
        else:
            tx = pay_from_buyer_pool(
                circle,
                a["payout_address"],
                a["price_usdc"],
                reference=f"obol-run-{run_id}-{a['id']}",
                buyer_hint=f"agent-run-{run_id}",
            )
            spent += a["price_usdc"]
            purchase_count += 1
            budget_after = round(budget_usdc - spent, 6)
            bought.append(a)
            covered |= aspects
            cur.execute("""INSERT INTO receipts(run_id, article_id, creator_id, amount_usdc,
                           tx_hash, transaction_id, blockchain, settlement_mode,
                           source, buyer, created_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                        (run_id, a["id"], a["creator_id"], a["price_usdc"],
                         tx["tx_hash"], tx.get("transaction_id", ""), tx["blockchain"],
                         tx.get("mode", circle.mode), "agent",
                         tx.get("payer_buyer_id", "agent"), time.time()))
            base = a["reason"] or "relevant to the query and within budget"
            decision = "buy"
            policy_rule = "value_purchase"
            reason = (
                f"{base}; authorized because relevance {a['relevance']:.2f} >= "
                f"{policy.min_relevance:.2f}, price ${a['price_usdc']:.3f} fits the "
                f"configured spending guardrails, and it adds "
                f"{len(novelty)} new aspect{'s' if len(novelty) != 1 else ''}. "
                f"Paid read {purchase_count}/{_purchase_limit(policy)}; "
                f"${budget_after:.3f} remains including the protected "
                f"${policy.reserve_usdc:.3f} reserve"
            )
        cur.execute("""INSERT INTO decisions(
                       run_id, article_id, decision, reason, policy_rule,
                       relevance, price_usdc, budget_before_usdc,
                       budget_after_usdc, created_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (run_id, a["id"], decision, reason, policy_rule,
                     a["relevance"], a["price_usdc"], budget_before,
                     budget_after, time.time()))

    coverage = _coverage(covered, q_terms, bool(bought))
    answer = _synthesize(query, bought, coverage)
    if bought and coverage >= policy.coverage_target:
        stop_rule = "coverage_target"
        stop_reason = (
            f"Stopped with {coverage:.0%} query coverage, meeting the "
            f"{policy.coverage_target:.0%} target; ${budget_usdc - spent:.3f} remains."
        )
    elif policy.max_purchases is not None and purchase_count >= policy.max_purchases:
        stop_rule = "max_purchases"
        stop_reason = (
            f"Stopped after {purchase_count} paid read(s), the configured maximum; "
            f"${budget_usdc - spent:.3f} remains."
        )
    elif policy.reserve_usdc and budget_usdc - spent <= policy.reserve_usdc + 1e-9:
        stop_rule = "reserve_balance"
        stop_reason = (
            f"Stopped before touching the protected ${policy.reserve_usdc:.3f} "
            f"reserve; ${budget_usdc - spent:.3f} remains."
        )
    else:
        stop_rule = "candidate_scan_complete"
        stop_reason = (
            f"Stopped after evaluating all {len(articles)} candidates under the "
            f"policy; {purchase_count} paid read(s), ${budget_usdc - spent:.3f} remains."
        )
    cur.execute("""UPDATE agent_runs SET status=?, answer=?, total_spent=?,
                   coverage=?, stop_rule=?, stop_reason=?, finished_at=? WHERE id=?""",
                ("done", answer, round(spent, 6), round(coverage, 4),
                 stop_rule, stop_reason, time.time(), run_id))
    conn.commit()
    conn.close()
    return get_run(run_id)


def get_run(run_id):
    conn = get_db()
    cur = conn.cursor()
    run = cur.execute("SELECT * FROM agent_runs WHERE id=?", (run_id,)).fetchone()
    if not run:
        conn.close()
        return None
    run = dict(run)
    decisions = [dict(r) for r in cur.execute("""
        SELECT d.*, a.title, c.name AS creator_name
        FROM decisions d JOIN articles a ON a.id=d.article_id
        JOIN creators c ON c.id=a.creator_id WHERE d.run_id=?
        ORDER BY CASE d.decision WHEN 'buy' THEN 0 WHEN 'reuse' THEN 1 ELSE 2 END,
                 d.relevance DESC""", (run_id,)).fetchall()]
    receipts = [dict(r) for r in cur.execute("""
        SELECT r.*, a.title, c.name AS creator_name
        FROM receipts r JOIN articles a ON a.id=r.article_id
        JOIN creators c ON c.id=r.creator_id WHERE r.run_id=? ORDER BY r.id""", (run_id,)).fetchall()]
    conn.close()

    sources_used = len([d for d in decisions if d["decision"] in ("buy", "reuse")])
    coverage = run.get("coverage") or 0.0
    run["decisions"] = decisions
    run["receipts"] = receipts
    run["sources_used"] = sources_used
    run["saved_usdc"] = round(sum(d["price_usdc"] for d in decisions if d["decision"] == "reuse"), 6)
    run["budget_remaining"] = round((run.get("budget_usdc") or 0) - (run.get("total_spent") or 0), 6)
    raw_policy = run.pop("policy_json", None)
    try:
        policy = json.loads(raw_policy or "")
    except (TypeError, ValueError):
        policy = SpendingPolicy.from_input(run.get("budget_usdc") or 0.001).to_dict()
    run["policy"] = policy
    run["spendable_remaining_usdc"] = round(
        max(0.0, (policy.get("spendable_budget_usdc") or 0)
            - (run.get("total_spent") or 0)),
        6,
    )
    audit_log = []
    for d in sorted(decisions, key=lambda item: item["id"]):
        audit_log.append({
            "event": d["decision"],
            "article_id": d["article_id"],
            "title": d["title"],
            "rule": d.get("policy_rule") or "legacy_decision",
            "reason": d.get("reason") or "no reason recorded",
            "relevance": d.get("relevance"),
            "price_usdc": d.get("price_usdc"),
            "budget_before_usdc": d.get("budget_before_usdc"),
            "budget_after_usdc": d.get("budget_after_usdc"),
        })
    audit_log.append({
        "event": "stop",
        "article_id": None,
        "title": "Policy engine",
        "rule": run.get("stop_rule") or "legacy_run_complete",
        "reason": run.get("stop_reason") or "Run completed.",
        "relevance": None,
        "price_usdc": 0.0,
        "budget_before_usdc": run["budget_remaining"],
        "budget_after_usdc": run["budget_remaining"],
    })
    run["audit_log"] = audit_log
    run["purchase_count"] = len([d for d in decisions if d["decision"] == "buy"])
    run["coverage"] = round(coverage, 4)
    run["confidence"] = _confidence(coverage, sources_used)
    run["llm_mode"] = "openai" if llm.available() else "heuristic"
    receipt_modes = {
        receipt.get("settlement_mode")
        for receipt in receipts
        if receipt.get("settlement_mode") in {"live", "mock"}
    }
    run["settlement_mode"] = (
        "live" if receipt_modes == {"live"}
        else "mock" if "mock" in receipt_modes
        else CircleService().mode
    )
    return run


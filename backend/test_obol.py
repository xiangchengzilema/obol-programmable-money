"""
Obol backend tests. Uses a throwaway DB + the seed data.
Run:  cd backend && python -m pytest -q
"""
import os
import tempfile

# Point everything at a temp DB BEFORE importing the app/db modules.
os.environ["OBOL_DB_PATH"] = os.path.join(tempfile.gettempdir(), "obol_test.db")
os.environ["OBOL_FORCE_MOCK"] = "1"
os.environ.setdefault("OBOL_MIN_RELEVANCE", "0.35")
if os.path.exists(os.environ["OBOL_DB_PATH"]):
    os.remove(os.environ["OBOL_DB_PATH"])

import seed
import app as appmod

seed.seed(force=True)
client = appmod.app.test_client()


def test_health():
    r = client.get("/api/health").get_json()
    assert r["status"] == "ok"
    assert r["settlement_mode"] in ("mock", "live")


def test_settlement_status_is_non_secret_and_explicit():
    r = client.get("/api/settlement/status").get_json()
    assert r["mode"] == "mock"
    assert r["force_mock"] is True
    assert r["blockchain"] == "ARC-TESTNET"
    assert "OBOL_FORCE_MOCK enabled" in r["missing"]
    assert "api_key" not in r
    assert "entity_secret" not in r


def test_frontend_is_served_by_backend():
    home = client.get("/")
    assert home.status_code == 200
    assert b"Obol" in home.data
    js = client.get("/app.js")
    assert js.status_code == 200
    assert b"Obol frontend" in js.data


def test_seeded_marketplace_is_locked():
    arts = client.get("/api/articles").get_json()
    assert len(arts) >= 4
    assert arts[0]["locked"] is True
    assert "content" not in arts[0]          # full content must stay paywalled


def test_create_creator_validates_address():
    bad = client.post("/api/creators", json={"name": "X", "payout_address": "nope"})
    assert bad.status_code == 400
    ok = client.post("/api/creators", json={
        "name": "Test Creator", "payout_address": "0x" + "a" * 40})
    assert ok.status_code == 201
    assert ok.get_json()["id"] > 0


def test_create_article_requires_fields():
    r = client.post("/api/articles", json={"creator_id": 1, "title": "no content"})
    assert r.status_code == 400


def test_agent_decides_within_budget():
    run = client.post("/api/agent/run", json={
        "query": "how do nanopayments and Arc fees work for agent APIs",
        "budget_usdc": 0.05}).get_json()
    assert run["status"] == "done"
    assert run["total_spent"] <= 0.05 + 1e-9          # never exceeds budget
    buys = [d for d in run["decisions"] if d["decision"] == "buy"]
    skips = [d for d in run["decisions"] if d["decision"] == "skip"]
    assert len(buys) >= 1                              # bought something relevant
    assert len(skips) >= 1                             # skipped something
    assert len(run["receipts"]) == len(buys)
    assert all(r["tx_hash"].startswith("0x") for r in run["receipts"])
    assert all(r["settlement_mode"] == "mock" for r in run["receipts"])


def test_agent_reuses_cache_on_second_run():
    q = {"query": "Arc testnet predictable fees nanopayments", "budget_usdc": 0.05}
    client.post("/api/agent/run", json=q)             # first run pays
    run2 = client.post("/api/agent/run", json=q).get_json()
    reuses = [d for d in run2["decisions"] if d["decision"] == "reuse"]
    assert len(reuses) >= 1                            # already-paid articles reused free
    assert run2["saved_usdc"] >= 0


def test_agent_run_reports_plan_coverage_confidence():
    run = client.post("/api/agent/run", json={
        "query": "nanopayments and Arc fees for agent APIs",
        "budget_usdc": 0.05}).get_json()
    assert run["plan"] and "budget" in run["plan"].lower()
    assert 0.0 <= run["coverage"] <= 1.0
    assert run["confidence"] in ("none", "low", "medium", "high")
    # budget accounting is internally consistent
    assert abs(run["budget_remaining"] - (run["budget_usdc"] - run["total_spent"])) < 1e-6
    assert run["sources_used"] == len([d for d in run["decisions"]
                                       if d["decision"] in ("buy", "reuse")])


def test_agent_stops_when_budget_is_generous():
    """With a huge budget the agent should still NOT buy everything — it stops once
    the question is covered (agency, not greedy spending)."""
    n_articles = client.get("/api/stats").get_json()["num_articles"]
    run = client.post("/api/agent/run", json={
        "query": "what are nanopayments", "budget_usdc": 999.0}).get_json()
    skips = [d for d in run["decisions"] if d["decision"] == "skip"]
    # acquired (bought or reused) at least one source, but NOT everything affordable
    assert 1 <= run["sources_used"] < n_articles
    assert len(skips) >= 1               # deliberately left sources unbought


def test_programmable_policy_enforces_reserve_and_purchase_cap():
    client.post("/api/demo/reset")
    run = client.post("/api/agent/run", json={
        "query": "Arc testnet predictable fees nanopayments agents x402",
        "budget_usdc": 0.05,
        "policy": {
            "reserve_usdc": 0.04,
            "max_price_usdc": 0.02,
            "min_relevance": 0.0,
            "max_purchases": 1,
            "coverage_target": 1.0,
        },
    }).get_json()

    assert run["status"] == "done"
    assert run["policy"] == {
        "total_budget_usdc": 0.05,
        "spendable_budget_usdc": 0.01,
        "reserve_usdc": 0.04,
        "max_price_usdc": 0.02,
        "min_relevance": 0.0,
        "max_purchases": 1,
        "coverage_target": 1.0,
    }
    assert run["purchase_count"] <= 1
    assert run["total_spent"] <= 0.01 + 1e-9
    assert run["budget_remaining"] >= 0.04 - 1e-9
    assert run["spendable_remaining_usdc"] >= -1e-9

    assert len(run["audit_log"]) == len(run["decisions"]) + 1
    assert run["audit_log"][-1]["event"] == "stop"
    assert run["audit_log"][-1]["rule"] in {
        "coverage_target", "max_purchases", "reserve_balance",
        "candidate_scan_complete",
    }
    for event in run["audit_log"]:
        assert event["rule"]
        assert event["reason"]
        assert event["budget_before_usdc"] is not None
        assert event["budget_after_usdc"] is not None


def test_programmable_policy_blocks_sources_above_price_cap():
    client.post("/api/demo/reset")
    run = client.post("/api/agent/run", json={
        "query": "Arc agents x402 creator receipts",
        "budget_usdc": 0.05,
        "policy": {
            "reserve_usdc": 0,
            "max_price_usdc": 0.009,
            "min_relevance": 0,
            "max_purchases": 5,
            "coverage_target": 1,
        },
    }).get_json()

    assert run["total_spent"] == 0
    assert run["purchase_count"] == 0
    assert run["receipts"] == []
    assert run["decisions"]
    assert all(d["decision"] == "skip" for d in run["decisions"])
    assert all(d["policy_rule"] == "max_price" for d in run["decisions"])
    assert all("per-source cap" in d["reason"] for d in run["decisions"])


def test_programmable_policy_validation_is_client_facing():
    invalid_policies = [
        ["not", "an", "object"],
        {"reserve_usdc": 0.06},
        {"max_price_usdc": -0.01},
        {"min_relevance": 1.1},
        {"max_purchases": 1.5},
        {"coverage_target": -0.1},
        {"coverage_target": 0},
        {"typo_budget": 0.01},
    ]
    for policy in invalid_policies:
        response = client.post("/api/agent/run", json={
            "query": "Arc fees",
            "budget_usdc": 0.05,
            "policy": policy,
        })
        assert response.status_code == 400
        assert response.get_json()["error"]


def test_stats_has_accountability_counters():
    s = client.get("/api/stats").get_json()
    assert s["decisions_made"] >= 1
    assert s["usdc_saved_by_reuse"] >= 0


def test_demo_reset_reseeds_clean_state():
    r = client.post("/api/demo/reset")
    assert r.status_code == 200
    assert r.get_json()["status"] == "reset"
    s = client.get("/api/stats").get_json()
    assert s["num_creators"] >= 4
    assert s["num_articles"] >= 6
    assert s["total_reads"] == 0


def test_x402_402_then_pay():
    # unpaid → 402 with a challenge
    r = client.get("/x402/articles/1")
    assert r.status_code == 402
    body = r.get_json()
    assert body["accepts"][0]["asset"] == "USDC"
    assert body["accepts"][0]["payTo"].startswith("0x")
    assert body["proofVerification"] == "demo-format-only"
    # pay → proof → content
    r2 = client.get("/x402/articles/1", headers={"X-Payment": "0x" + "b" * 64})
    assert r2.status_code == 200
    assert "content" in r2.get_json()
    assert r2.get_json()["receipt"]["source"] == "x402"
    assert r2.get_json()["receipt"]["settlement_mode"] == "mock"


def test_x402_replay_is_idempotent_but_bound_to_resource():
    client.post("/api/demo/reset")
    proof = "0x" + "c" * 64
    first = client.get("/x402/articles/1", headers={"X-Payment": proof}).get_json()
    again = client.get("/x402/articles/1", headers={"X-Payment": proof}).get_json()
    assert again["receipt"]["id"] == first["receipt"]["id"]
    assert client.get("/api/stats").get_json()["total_reads"] == 1

    cross = client.get("/x402/articles/2", headers={"X-Payment": proof})
    assert cross.status_code == 402
    assert "already used" in cross.get_json()["error"]


def test_external_receipts_do_not_prime_agent_cache():
    client.post("/api/demo/reset")
    client.get("/x402/articles/4", headers={"X-Payment": "0x" + "d" * 64})
    run = client.post("/api/agent/run", json={
        "query": "Arc testnet predictable fees",
        "budget_usdc": 0.05}).get_json()
    arc_decision = [d for d in run["decisions"] if d["article_id"] == 4][0]
    assert arc_decision["decision"] == "buy"


def test_unlock_returns_content_and_receipt():
    r = client.post("/api/articles/2/unlock", json={"buyer": "tester"})
    assert r.status_code == 201
    body = r.get_json()
    assert body["content"]
    assert body["receipt"]["amount_usdc"] > 0
    assert body["payer_buyer_id"]


def test_unlock_uses_buyer_wallet_pool(monkeypatch):
    calls = []

    def fake_pay_from_buyer_pool(circle, to_address, amount_usdc, reference="", buyer_hint=""):
        calls.append({
            "to_address": to_address,
            "amount_usdc": amount_usdc,
            "reference": reference,
            "buyer_hint": buyer_hint,
        })
        return {
            "tx_hash": "0x" + "e" * 64,
            "transaction_id": "fake-tx",
            "blockchain": "ARC-TESTNET",
            "payer_buyer_id": "buyer-007",
            "payer_address": "0x" + "7" * 40,
        }

    monkeypatch.setattr(appmod, "pay_from_buyer_pool", fake_pay_from_buyer_pool)
    r = client.post("/api/articles/2/unlock", json={"buyer": "tester"})
    assert r.status_code == 201
    body = r.get_json()
    assert calls
    assert calls[0]["buyer_hint"] == "tester"
    assert body["payer_buyer_id"] == "buyer-007"


def test_unlock_settlement_failure_is_structured(monkeypatch):
    class FailingCircle:
        def send_usdc_from_wallet(self, *_args, **_kwargs):
            raise RuntimeError("simulated Circle outage")

    monkeypatch.setattr(appmod, "CircleService", lambda: FailingCircle())
    r = client.post("/api/articles/2/unlock", json={"buyer": "tester"})
    assert r.status_code == 502
    assert "settlement failed" in r.get_json()["error"]


def test_stats_and_ledger_grow():
    stats = client.get("/api/stats").get_json()
    assert stats["total_reads"] >= 1
    assert stats["total_paid_usdc"] >= 0
    ledger = client.get("/api/ledger").get_json()
    assert len(ledger) >= 1
    assert ledger[0]["tx_hash"].startswith("0x")


def test_public_demo_blocks_management_and_caps_budget(monkeypatch):
    monkeypatch.setenv("OBOL_PUBLIC_DEMO", "1")
    monkeypatch.setenv("OBOL_PUBLIC_MAX_BUDGET_USDC", "0.10")

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.get_json()["public_demo"] is True
    assert health.get_json()["settlement_mode"] == "mock"

    create = client.post("/api/creators", json={
        "name": "Blocked",
        "payout_address": "0x" + "a" * 40,
    })
    assert create.status_code == 403

    reset = client.post("/api/demo/reset")
    assert reset.status_code == 403

    too_large = client.post("/api/agent/run", json={
        "query": "Arc agent payments",
        "budget_usdc": 0.11,
    })
    assert too_large.status_code == 400
    assert "public demo budget" in too_large.get_json()["error"]


def test_public_x402_demo_receipt_is_not_persisted(monkeypatch):
    client.post("/api/demo/reset")
    before = client.get("/api/stats").get_json()
    monkeypatch.setenv("OBOL_PUBLIC_DEMO", "1")

    paid = client.get(
        "/x402/articles/1",
        headers={
            "X-Payment": "0x" + "9" * 64,
            "X-Payer": "public-demo-agent",
        },
    )
    assert paid.status_code == 200
    receipt = paid.get_json()["receipt"]
    assert receipt["settlement_mode"] == "mock"
    assert receipt["persisted"] is False
    assert receipt["source"] == "x402-demo"
    assert receipt["blockchain"] == "SIMULATED-ARC-TESTNET"

    after = client.get("/api/stats").get_json()
    assert after["total_reads"] == before["total_reads"]
    assert after["total_paid_usdc"] == before["total_paid_usdc"]


def test_stats_separate_live_and_demo_receipts():
    client.post("/api/demo/reset")
    client.post("/api/agent/run", json={
        "query": "Arc payments",
        "budget_usdc": 0.05,
    })
    stats = client.get("/api/stats").get_json()
    assert stats["live_reads"] == 0
    assert stats["live_paid_usdc"] == 0
    assert stats["demo_reads"] == stats["total_reads"]
    assert stats["demo_paid_usdc"] == stats["total_paid_usdc"]


def test_live_x402_refuses_unverified_proof(monkeypatch):
    class LiveCircle:
        mode = "live"

    monkeypatch.delenv("OBOL_PUBLIC_DEMO", raising=False)
    monkeypatch.delenv("OBOL_ALLOW_UNVERIFIED_X402_PROOFS", raising=False)
    monkeypatch.setattr(appmod, "CircleService", lambda: LiveCircle())

    paid = client.get(
        "/x402/articles/1",
        headers={"X-Payment": "0x" + "f" * 64},
    )
    assert paid.status_code == 501
    assert "refusing an unverified payment proof" in paid.get_json()["error"]

"""
Obol backend tests. Uses a throwaway DB + the seed data.
Run:  cd backend && python -m pytest -q
"""
import os
import tempfile
import pytest

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


def test_latest_evidence_is_public_and_matches_verified_transfer():
    response = client.get("/api/evidence/latest")
    assert response.status_code == 200
    evidence = response.get_json()
    assert evidence["circle"]["state"] == "COMPLETE"
    assert evidence["arc"]["network"] == "Arc Testnet"
    assert evidence["arc"]["amount_usdc"] == 0.01
    assert evidence["arc"]["transaction_hash"].startswith("0x")
    assert evidence["agent_run"]["total_spent_usdc"] <= evidence["agent_run"]["budget_usdc"]
    assert "api_key" not in str(evidence).lower()
    assert "entity_secret" not in str(evidence).lower()


def test_arc_transaction_verification_returns_safe_fields(monkeypatch):
    tx_hash = "0x" + "a" * 64
    block_hash = "0x" + "b" * 64
    secret = "provider-key-must-not-leak"
    monkeypatch.setenv(
        "ARC_RPC_URL",
        f"https://private-rpc.example/v1/{secret}?token={secret}",
    )
    monkeypatch.setattr(appmod, "_load_latest_evidence", lambda: {
        "evidence_id": "test-bound-evidence",
        "circle": {"state": "COMPLETE"},
        "arc": {
            "chain_id": 5042002,
            "transaction_hash": tx_hash,
            "payer_address": "0x" + "1" * 40,
            "creator_address": "0x" + "3" * 40,
            "token_contract": appmod.arc_verifier.ARC_USDC_ADDRESS,
            "amount_base_units": 10000,
            "block_number": 16,
            "block_hash": block_hash,
        },
    })

    def fake_rpc_call(rpc_url, method, params, timeout=8):
        assert secret in rpc_url
        responses = {
            "eth_chainId": "0x4cef52",
            "eth_getTransactionReceipt": {
                "transactionHash": tx_hash,
                "status": "0x1",
                "blockNumber": "0x10",
                "blockHash": block_hash,
                "transactionIndex": "0x2",
                "gasUsed": "0x5208",
                "cumulativeGasUsed": "0x10410",
                "effectiveGasPrice": "0x3b9aca00",
                "contractAddress": None,
                "logs": [{
                    "address": appmod.arc_verifier.ARC_USDC_ADDRESS,
                    "topics": [
                        appmod.arc_verifier.ERC20_TRANSFER_TOPIC,
                        "0x" + "0" * 24 + "1" * 40,
                        "0x" + "0" * 24 + "3" * 40,
                    ],
                    "data": "0x2710",
                }],
            },
            "eth_getTransactionByHash": {
                "hash": tx_hash,
                "from": "0x" + "1" * 40,
                "to": appmod.arc_verifier.ARC_USDC_ADDRESS,
                "value": "0xf4240",
                "nonce": "0x7",
                "input": "0x1234",
                "blockNumber": "0x10",
                "blockHash": block_hash,
                "transactionIndex": "0x2",
            },
            "eth_getBlockByNumber": {
                "number": "0x10",
                "hash": block_hash,
                "timestamp": "0x66b3c780",
            },
        }
        return responses[method]

    monkeypatch.setattr(appmod.arc_verifier, "_rpc_call", fake_rpc_call)
    response = client.get(f"/api/arc/transactions/{tx_hash}/verify")

    assert response.status_code == 200
    body = response.get_json()
    assert body["network"] == "arc-testnet"
    assert body["chain_id"] == 5042002
    assert body["rpc_host"] == "configured-rpc"
    assert body["confirmed"] is True
    assert body["verified"] is True
    assert body["successful"] is True
    assert body["status"] == "success"
    assert body["transaction"] == {
        "hash": tx_hash,
        "from": "0x" + "1" * 40,
        "to": appmod.arc_verifier.ARC_USDC_ADDRESS,
        "block_number": 16,
        "block_hash": block_hash,
        "value_wei": "1000000",
        "nonce": 7,
        "input_bytes": 2,
    }
    assert body["receipt"]["block_number"] == 16
    assert body["receipt"]["transaction_hash"] == tx_hash
    assert body["receipt"]["gas_used"] == 21000
    assert body["receipt"]["effective_gas_price_wei"] == "1000000000"
    assert body["receipt"]["usdc_transfers"] == [{
        "token_contract": appmod.arc_verifier.ARC_USDC_ADDRESS,
        "from": "0x" + "1" * 40,
        "to": "0x" + "3" * 40,
        "amount_base_units": 10000,
        "amount_usdc": "0.010000",
    }]
    assert body["block"]["timestamp"] == int("66b3c780", 16)
    assert body["block"]["timestamp_iso"].endswith("Z")
    assert body["block"]["hash"] == block_hash
    assert body["evidence_match"] is True
    assert body["evidence_id"] == "test-bound-evidence"
    assert body["matched_transfer"]["from"] == "0x" + "1" * 40
    assert secret not in response.get_data(as_text=True)


def test_arc_transaction_verification_rejects_invalid_hash_without_rpc(monkeypatch):
    def network_must_not_run(*_args, **_kwargs):
        raise AssertionError("invalid hashes must be rejected before RPC")

    monkeypatch.setattr(appmod.arc_verifier, "_rpc_call", network_must_not_run)
    response = client.get("/api/arc/transactions/not-a-hash/verify")
    assert response.status_code == 400
    assert "0x followed by 64 hex" in response.get_json()["error"]


def test_arc_transaction_verification_falls_back_and_sanitizes_rpc_errors(monkeypatch):
    monkeypatch.delenv("ARC_RPC_URL", raising=False)
    attempted_hosts = []

    def unavailable(rpc_url, *_args, **_kwargs):
        attempted_hosts.append(appmod.arc_verifier._rpc_hostname(rpc_url))
        raise appmod.arc_verifier.ArcRPCError("upstream detail must stay private")

    monkeypatch.setattr(appmod.arc_verifier, "_rpc_call", unavailable)
    tx_hash = "0x" + "c" * 64
    monkeypatch.setattr(appmod, "_load_latest_evidence", lambda: {
        "evidence_id": "unavailable-test",
        "circle": {"state": "COMPLETE"},
        "arc": {
            "chain_id": 5042002,
            "transaction_hash": tx_hash,
            "payer_address": "0x" + "1" * 40,
            "creator_address": "0x" + "2" * 40,
            "token_contract": appmod.arc_verifier.ARC_USDC_ADDRESS,
            "amount_base_units": 1,
            "block_number": 1,
            "block_hash": "0x" + "f" * 64,
        },
    })
    response = client.get(f"/api/arc/transactions/{tx_hash}/verify")

    assert response.status_code == 502
    assert attempted_hosts == ["rpc.testnet.arc.network", "rpc.testnet.arc.io"]
    body = response.get_json()
    assert body == {
        "error": "Arc evidence verification is temporarily unavailable",
        "network": "arc-testnet",
        "rpc_hosts": ["rpc.testnet.arc.network", "rpc.testnet.arc.io"],
    }
    assert "upstream detail" not in response.get_data(as_text=True)


def test_arc_transaction_verification_returns_404_when_all_rpcs_agree(monkeypatch):
    monkeypatch.delenv("ARC_RPC_URL", raising=False)

    def not_found(_rpc_url, method, _params, timeout=8):
        if method == "eth_chainId":
            return "0x4cef52"
        if method in {"eth_getTransactionReceipt", "eth_getTransactionByHash"}:
            return None
        raise AssertionError(f"unexpected method: {method}")

    monkeypatch.setattr(appmod.arc_verifier, "_rpc_call", not_found)
    tx_hash = "0x" + "d" * 64
    monkeypatch.setattr(appmod, "_load_latest_evidence", lambda: {
        "evidence_id": "missing-test",
        "circle": {"state": "COMPLETE"},
        "arc": {
            "chain_id": 5042002,
            "transaction_hash": tx_hash,
            "payer_address": "0x" + "1" * 40,
            "creator_address": "0x" + "2" * 40,
            "token_contract": appmod.arc_verifier.ARC_USDC_ADDRESS,
            "amount_base_units": 1,
            "block_number": 1,
            "block_hash": "0x" + "f" * 64,
        },
    })
    response = client.get(f"/api/arc/transactions/{tx_hash}/verify")

    assert response.status_code == 404
    body = response.get_json()
    assert body["tx_hash"] == tx_hash
    assert body["network"] == "arc-testnet"
    assert body["rpc_hosts"] == ["rpc.testnet.arc.network", "rpc.testnet.arc.io"]


def test_arc_verifier_rejects_uncommitted_hash_before_rpc(monkeypatch):
    called = False

    def network_must_not_run(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("uncommitted hashes must not reach RPC")

    monkeypatch.setattr(appmod.arc_verifier, "_rpc_call", network_must_not_run)
    response = client.get("/api/arc/transactions/0x" + "e" * 64 + "/verify")
    assert response.status_code == 404
    assert called is False


def test_arc_rpc_rejects_receipt_for_a_different_transaction(monkeypatch):
    tx_hash = "0x" + "1" * 64
    other_hash = "0x" + "2" * 64

    def mismatched_receipt(_rpc_url, method, _params, timeout=8):
        responses = {
            "eth_chainId": "0x4cef52",
            "eth_getTransactionReceipt": {
                "transactionHash": other_hash,
                "status": "0x1",
                "blockNumber": "0x10",
                "blockHash": "0x" + "3" * 64,
                "transactionIndex": "0x0",
                "logs": [],
            },
            "eth_getTransactionByHash": {
                "hash": tx_hash,
                "from": "0x" + "4" * 40,
                "to": appmod.arc_verifier.ARC_USDC_ADDRESS,
                "value": "0x0",
                "nonce": "0x0",
                "input": "0x",
                "blockNumber": "0x10",
                "blockHash": "0x" + "3" * 64,
                "transactionIndex": "0x0",
            },
        }
        return responses[method]

    monkeypatch.setattr(appmod.arc_verifier, "_rpc_call", mismatched_receipt)
    with pytest.raises(appmod.arc_verifier.ArcRPCError, match="different transaction"):
        appmod.arc_verifier._verify_with_rpc(tx_hash, "https://rpc.testnet.arc.network")


def test_evidence_binding_rejects_same_recipient_and_amount_from_wrong_payer(monkeypatch):
    tx_hash = "0x" + "5" * 64
    block_hash = "0x" + "6" * 64
    payer = "0x" + "7" * 40
    wrong_payer = "0x" + "8" * 40
    creator = "0x" + "9" * 40
    token = appmod.arc_verifier.ARC_USDC_ADDRESS
    evidence = {
        "evidence_id": "payer-binding-test",
        "circle": {"state": "COMPLETE"},
        "arc": {
            "chain_id": 5042002,
            "transaction_hash": tx_hash,
            "payer_address": payer,
            "creator_address": creator,
            "token_contract": token,
            "amount_base_units": 10000,
            "block_number": 16,
            "block_hash": block_hash,
        },
    }
    monkeypatch.setattr(appmod.arc_verifier, "verify_transaction", lambda _hash: {
        "verified": True,
        "successful": True,
        "chain_id": 5042002,
        "transaction": {
            "hash": tx_hash,
            "from": payer,
            "to": token,
            "block_number": 16,
            "block_hash": block_hash,
        },
        "receipt": {
            "transaction_hash": tx_hash,
            "block_number": 16,
            "block_hash": block_hash,
            "usdc_transfers": [{
                "token_contract": token,
                "from": wrong_payer,
                "to": creator,
                "amount_base_units": 10000,
            }],
        },
        "block": {"number": 16, "hash": block_hash},
    })
    with pytest.raises(appmod.arc_verifier.ArcRPCError, match="does not match"):
        appmod.arc_verifier.verify_evidence_bundle(evidence)


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


def test_x402_preflight_allows_machine_payment_headers(monkeypatch):
    monkeypatch.setenv("OBOL_PUBLIC_DEMO", "1")
    response = client.options(
        "/x402/articles/1",
        headers={
            "Origin": "https://judge.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Payment, X-Payer",
        },
    )
    assert response.status_code == 204
    assert response.headers["Access-Control-Allow-Origin"] == "*"
    allowed = response.headers["Access-Control-Allow-Headers"].lower()
    assert "x-payment" in allowed
    assert "x-payer" in allowed


def test_x402_replay_is_idempotent_but_bound_to_resource():
    client.post("/api/demo/reset")
    proof = "0x" + "c" * 64
    first = client.get("/x402/articles/1", headers={"X-Payment": proof}).get_json()
    again = client.get("/x402/articles/1", headers={"X-Payment": proof}).get_json()
    assert again["receipt"]["id"] == first["receipt"]["id"]
    assert client.get("/api/stats").get_json()["demo_reads"] == 1

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
    r = client.post("/api/articles/2/unlock", json={"buyer": "content-tester"})
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
    r = client.post("/api/articles/2/unlock", json={"buyer": "pool-tester"})
    assert r.status_code == 201
    body = r.get_json()
    assert calls
    assert calls[0]["buyer_hint"] == "pool-tester"
    assert body["payer_buyer_id"] == "buyer-007"


def test_unlock_settlement_failure_is_structured(monkeypatch):
    class FailingCircle:
        mode = "mock"

        def send_usdc_from_wallet(self, *_args, **_kwargs):
            raise RuntimeError("simulated Circle outage")

    monkeypatch.setattr(appmod, "CircleService", lambda: FailingCircle())
    r = client.post("/api/articles/2/unlock", json={"buyer": "outage-tester"})
    assert r.status_code == 202
    assert r.get_json()["status"] == "settlement_pending"
    assert "content" not in r.get_json()


def test_stats_and_ledger_grow():
    stats = client.get("/api/stats").get_json()
    assert stats["settled_receipts"] >= 1
    assert stats["settled_receipt_volume_usdc"] >= 0
    ledger = client.get("/api/ledger").get_json()
    assert len(ledger) >= 1
    settled = [r for r in ledger if r["settlement_mode"] in {"live", "mock"}]
    assert settled and all(r["tx_hash"].startswith("0x") for r in settled)


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
    assert stats["total_reads"] == 0
    assert stats["total_paid_usdc"] == 0
    assert stats["demo_reads"] == stats["settled_receipts"]
    assert stats["demo_paid_usdc"] == stats["settled_receipt_volume_usdc"]


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


class _FakeLiveCircle:
    mode = "live"

    from circle_service import CircleService as _RealCircleService
    settlement_mode_for_transaction = staticmethod(
        _RealCircleService.settlement_mode_for_transaction
    )

    def __init__(self):
        self._sequence = 0

    def _transaction(self):
        self._sequence += 1
        return {
            "tx_hash": "0x" + f"{self._sequence:064x}",
            "transaction_id": f"circle-test-{self._sequence}",
            "blockchain": "ARC-TESTNET",
            "state": "COMPLETE",
            "mode": "live",
        }

    def send_usdc(self, *_args, **_kwargs):
        return self._transaction()

    def send_usdc_from_wallet(self, *_args, **_kwargs):
        return self._transaction()


class _FakePendingCircle(_FakeLiveCircle):
    def _transaction(self):
        tx = super()._transaction()
        tx["state"] = "INITIATED"
        return tx


def _receipt_modes(source):
    from db import get_db

    conn = get_db()
    modes = [
        row["settlement_mode"]
        for row in conn.execute(
            "SELECT settlement_mode FROM receipts WHERE source=? ORDER BY id",
            (source,),
        ).fetchall()
    ]
    conn.close()
    return modes


def test_demo_revenue_records_explicit_live_settlement_mode(monkeypatch):
    import demo_revenue

    seed.seed(force=True)
    monkeypatch.setattr(demo_revenue, "CircleService", _FakeLiveCircle)

    result = demo_revenue.execute(
        target_usdc=0.001,
        live=True,
        create_creator_wallets=False,
    )

    assert result["payments"]
    assert set(_receipt_modes(demo_revenue.SOURCE)) == {"live"}


def test_usage_simulator_records_mock_and_live_modes(monkeypatch):
    import usage_simulator

    buyer = {
        "buyer_id": "buyer-001",
        "wallet_id": "wallet-001",
        "address": "0x" + "1" * 40,
        "state": "LIVE",
    }
    monkeypatch.setattr(
        usage_simulator,
        "select_buyers",
        lambda *_args, **_kwargs: [buyer],
    )
    monkeypatch.setattr(usage_simulator, "_log", lambda _event: None)

    seed.seed(force=True)
    usage_simulator.run_purchases(1, 1, live=False)
    assert _receipt_modes("usage-sim") == ["mock"]

    seed.seed(force=True)
    monkeypatch.setattr(usage_simulator, "CircleService", _FakeLiveCircle)
    usage_simulator.run_purchases(1, 1, live=True)
    assert _receipt_modes("usage-sim") == ["live"]


def test_buyer_topup_records_explicit_live_settlement_mode(monkeypatch):
    import topup_creator_revenue_from_buyers as topup
    from db import get_db

    seed.seed(force=True)
    conn = get_db()
    names = [row["name"] for row in conn.execute(
        "SELECT name FROM creators ORDER BY id"
    ).fetchall()]
    conn.close()
    targets = {name: 0 for name in names}
    targets[names[0]] = 0.001
    buyer = {
        "buyer_id": "buyer-001",
        "wallet_id": "wallet-001",
        "address": "0x" + "1" * 40,
        "state": "LIVE",
    }
    monkeypatch.setattr(topup, "buyer_wallets", lambda: [buyer])
    monkeypatch.setattr(topup, "CircleService", _FakeLiveCircle)

    result = topup.run(targets, buyer_start=1, buyer_end=1, dry_run=False)

    assert len(result["payments"]) == 1
    assert _receipt_modes("usage-sim") == ["live"]


def test_pending_circle_transactions_never_count_as_live(monkeypatch):
    import demo_revenue
    import topup_creator_revenue_from_buyers as topup
    import usage_simulator
    from db import get_db

    seed.seed(force=True)
    monkeypatch.setattr(demo_revenue, "CircleService", _FakePendingCircle)
    demo_result = demo_revenue.execute(
        target_usdc=0.001,
        live=True,
        create_creator_wallets=False,
    )
    assert demo_result["payments"]
    assert {p["settlement_mode"] for p in demo_result["payments"]} == {"pending"}
    assert set(_receipt_modes(demo_revenue.SOURCE)) == {"pending"}
    assert all(row["earned_usdc"] == 0 for row in demo_result["summary"])
    assert all(not row["target_met"] for row in demo_result["summary"])

    seed.seed(force=True)
    buyer = {
        "buyer_id": "buyer-001",
        "wallet_id": "wallet-001",
        "address": "0x" + "1" * 40,
        "state": "LIVE",
    }
    monkeypatch.setattr(usage_simulator, "select_buyers", lambda *_args, **_kwargs: [buyer])
    monkeypatch.setattr(usage_simulator, "_log", lambda _event: None)
    monkeypatch.setattr(usage_simulator, "CircleService", _FakePendingCircle)
    results = usage_simulator.run_purchases(1, 1, live=True)
    assert results[0]["event"] == "settlement_pending"
    assert _receipt_modes("usage-sim") == ["pending"]
    assert all(row["earned_usdc"] == 0 for row in usage_simulator.summarize())

    seed.seed(force=True)
    conn = get_db()
    names = [row["name"] for row in conn.execute(
        "SELECT name FROM creators ORDER BY id"
    ).fetchall()]
    conn.close()
    targets = {name: 0 for name in names}
    targets[names[0]] = 0.001
    monkeypatch.setattr(topup, "buyer_wallets", lambda: [buyer])
    monkeypatch.setattr(topup, "CircleService", _FakePendingCircle)
    result = topup.run(targets, buyer_start=1, buyer_end=1, dry_run=False)
    assert result["payments"][0]["status"] == "pending"
    assert _receipt_modes("usage-sim") == ["pending"]
    assert result["summary"][0]["earned_usdc"] == 0
    assert result["summary"][0]["pending_receipts"] == 1


def test_usage_unknown_outcome_is_persisted_and_not_repaid(monkeypatch):
    import usage_simulator
    from db import get_db

    seed.seed(force=True)
    conn = get_db()
    article = dict(conn.execute("""
        SELECT a.*, c.name AS creator_name, c.payout_address
        FROM articles a JOIN creators c ON c.id=a.creator_id
        ORDER BY a.id LIMIT 1
    """).fetchone())
    conn.close()
    buyer = {
        "buyer_id": "buyer-001", "wallet_id": "wallet-001",
        "address": "0x" + "1" * 40, "state": "LIVE",
    }

    class UnknownCircle(_FakeLiveCircle):
        calls = 0

        def send_usdc_from_wallet(self, *_args, **_kwargs):
            type(self).calls += 1
            raise TimeoutError("response lost after submission")

    monkeypatch.setattr(usage_simulator, "select_buyers", lambda *_a, **_k: [buyer])
    monkeypatch.setattr(usage_simulator, "choose_article", lambda *_a, **_k: article)
    monkeypatch.setattr(usage_simulator, "_log", lambda _event: None)
    monkeypatch.setattr(usage_simulator, "CircleService", UnknownCircle)

    first = usage_simulator.run_purchases(1, 1, live=True)
    second = usage_simulator.run_purchases(1, 1, live=True)

    assert first[0]["event"] == "settlement_pending"
    assert second[0]["event"] == "settlement_pending"
    assert UnknownCircle.calls == 1
    assert _receipt_modes("usage-sim") == ["pending"]


def test_demo_revenue_unknown_outcome_is_not_repaid(monkeypatch):
    import demo_revenue

    seed.seed(force=True)

    class UnknownCircle(_FakeLiveCircle):
        calls = 0

        def send_usdc(self, *_args, **_kwargs):
            type(self).calls += 1
            raise TimeoutError("Circle response was lost")

    monkeypatch.setattr(demo_revenue, "CircleService", UnknownCircle)
    first = demo_revenue.execute(
        target_usdc=0.001, live=True, create_creator_wallets=False
    )
    calls_after_first = UnknownCircle.calls
    second = demo_revenue.execute(
        target_usdc=0.001, live=True, create_creator_wallets=False
    )

    assert calls_after_first == 9
    assert UnknownCircle.calls == calls_after_first
    assert {p["settlement_mode"] for p in first["payments"]} == {"pending"}
    assert {p["settlement_mode"] for p in second["payments"]} == {"pending"}
    assert set(_receipt_modes(demo_revenue.SOURCE)) == {"pending"}
    assert all(row["earned_usdc"] == 0 for row in second["summary"])


def test_utility_summaries_separate_settled_pending_and_unverified():
    import demo_revenue
    import topup_creator_revenue_from_buyers as topup
    import usage_simulator
    from db import get_db
    import time

    seed.seed(force=True)
    conn = get_db()
    article = conn.execute(
        """SELECT a.id, a.creator_id, c.name AS creator_name
           FROM articles a JOIN creators c ON c.id=a.creator_id
           ORDER BY a.id LIMIT 1"""
    ).fetchone()
    modes = [
        ("live", "live", 0.01),
        ("mock", "mock", 0.02),
        ("pending", "live", 0.03),
        ("failed", "live", 0.04),
        ("legacy", "legacy", 0.05),
    ]
    for idx, (mode, scope, amount) in enumerate(modes):
        conn.execute(
            """INSERT INTO receipts(run_id, article_id, creator_id, amount_usdc,
               tx_hash, transaction_id, blockchain, settlement_mode,
               settlement_scope, source, buyer, created_at)
               VALUES(NULL,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                article["id"], article["creator_id"], amount,
                "0x" + f"{idx + 1:064x}", f"summary-{idx}", "ARC-TESTNET",
                mode, scope, "usage-sim", f"summary-buyer-{idx}", time.time(),
            ),
        )
    conn.commit()

    demo_row = demo_revenue._earned_by_creator(conn, "live")[article["creator_id"]]
    assert demo_row["earned"] == 0.01
    assert demo_row["live_earned_usdc"] == 0.01
    assert demo_row["mock_earned_usdc"] == 0.02
    assert demo_row["pending_usdc"] == 0.03
    assert demo_row["unverified_usdc"] == 0.12
    topup_row = next(r for r in topup._current(conn) if r["id"] == article["creator_id"])
    assert topup_row["earned_usdc"] == 0.01
    assert topup_row["mock_earned_usdc"] == 0.02
    assert topup_row["pending_usdc"] == 0.03
    assert topup_row["unverified_usdc"] == 0.12
    conn.close()

    usage_row = next(r for r in usage_simulator.summarize()
                     if r["name"] == article["creator_name"])
    assert usage_row["earned_usdc"] == 0.03
    assert usage_row["pending_usdc"] == 0.03
    assert usage_row["unverified_usdc"] == 0.12


def test_usage_mock_claim_does_not_block_live_payment(monkeypatch):
    import usage_simulator
    from db import get_db

    seed.seed(force=True)
    conn = get_db()
    article = dict(conn.execute("""
        SELECT a.*, c.name AS creator_name, c.payout_address
        FROM articles a JOIN creators c ON c.id=a.creator_id
        ORDER BY a.id LIMIT 1
    """).fetchone())
    conn.close()
    buyer = {
        "buyer_id": "buyer-001", "wallet_id": "wallet-001",
        "address": "0x" + "1" * 40, "state": "LIVE",
    }

    class CountingLiveCircle(_FakeLiveCircle):
        calls = 0

        def send_usdc_from_wallet(self, *args, **kwargs):
            type(self).calls += 1
            return super().send_usdc_from_wallet(*args, **kwargs)

    monkeypatch.setattr(usage_simulator, "select_buyers", lambda *_a, **_k: [buyer])
    monkeypatch.setattr(usage_simulator, "choose_article", lambda *_a, **_k: article)
    monkeypatch.setattr(usage_simulator, "_log", lambda _event: None)
    usage_simulator.run_purchases(1, 1, live=False)
    monkeypatch.setattr(usage_simulator, "CircleService", CountingLiveCircle)
    live_result = usage_simulator.run_purchases(1, 1, live=True)

    assert live_result[0]["event"] == "paid_read"
    assert CountingLiveCircle.calls == 1
    assert _receipt_modes("usage-sim") == ["mock", "live"]


def test_usage_reconcile_promotes_pending_only_after_complete_hash(monkeypatch):
    import usage_simulator
    from db import get_db

    seed.seed(force=True)
    conn = get_db()
    article = dict(conn.execute("""
        SELECT a.*, c.name AS creator_name, c.payout_address
        FROM articles a JOIN creators c ON c.id=a.creator_id
        ORDER BY a.id LIMIT 1
    """).fetchone())
    conn.close()
    buyer = {
        "buyer_id": "buyer-001", "wallet_id": "wallet-001",
        "address": "0x" + "1" * 40, "state": "LIVE",
    }
    monkeypatch.setattr(usage_simulator, "select_buyers", lambda *_a, **_k: [buyer])
    monkeypatch.setattr(usage_simulator, "choose_article", lambda *_a, **_k: article)
    monkeypatch.setattr(usage_simulator, "_log", lambda _event: None)
    monkeypatch.setattr(usage_simulator, "CircleService", _FakePendingCircle)
    usage_simulator.run_purchases(1, 1, live=True)

    class ReconciledCircle(_FakeLiveCircle):
        def get_transaction(self, transaction_id):
            return {
                "id": transaction_id,
                "state": "COMPLETE",
                "txHash": "0x" + "c" * 64,
            }

    monkeypatch.setattr(usage_simulator, "CircleService", ReconciledCircle)
    reconciled = usage_simulator.reconcile_receipts()

    assert reconciled[0]["settlement_mode"] == "live"
    assert _receipt_modes("usage-sim") == ["live"]
    conn = get_db()
    row = conn.execute(
        "SELECT tx_hash FROM receipts WHERE source='usage-sim'"
    ).fetchone()
    conn.close()
    assert row["tx_hash"] == "0x" + "c" * 64


def test_topup_unknown_outcome_never_switches_wallet_or_repays(monkeypatch):
    import topup_creator_revenue_from_buyers as topup
    from db import get_db

    seed.seed(force=True)
    conn = get_db()
    names = [r["name"] for r in conn.execute(
        "SELECT name FROM creators ORDER BY id"
    ).fetchall()]
    conn.close()
    targets = {name: 0 for name in names}
    targets[names[0]] = 0.001
    buyers = [
        {
            "buyer_id": f"buyer-{idx:03d}", "wallet_id": f"wallet-{idx:03d}",
            "address": "0x" + f"{idx:040x}", "state": "LIVE",
        }
        for idx in (1, 2)
    ]

    class UnknownCircle(_FakeLiveCircle):
        calls = []

        def send_usdc_from_wallet(self, wallet_id, *_args, **_kwargs):
            type(self).calls.append(wallet_id)
            raise TimeoutError("Circle response was lost")

    monkeypatch.setattr(topup, "buyer_wallets", lambda: buyers)
    monkeypatch.setattr(topup, "CircleService", UnknownCircle)

    first = topup.run(targets, buyer_start=1, buyer_end=2, dry_run=False)
    second = topup.run(targets, buyer_start=1, buyer_end=2, dry_run=False)

    assert first["payments"][0]["status"] == "pending"
    assert second["payments"][0]["status"] == "pending"
    assert UnknownCircle.calls == ["wallet-001"]
    assert _receipt_modes("usage-sim") == ["pending"]


def test_restore_usage_log_preserves_live_mock_and_unknown_modes(monkeypatch, tmp_path):
    import restore_usage_log
    import json

    events = [
        {
            "event": "paid_read",
            "live": True,
            "state": "COMPLETE",
            "article_id": 1,
            "creator": "Alice Chen",
            "amount_usdc": 0.001,
            "tx_hash": "0x" + "a" * 64,
            "transaction_id": "circle-live",
            "buyer": "buyer-live",
        },
        {
            "event": "paid_read",
            "live": False,
            "article_id": 2,
            "creator": "Alice Chen",
            "amount_usdc": 0.001,
            "tx_hash": "0x" + "b" * 64,
            "transaction_id": "dry-mock",
            "buyer": "buyer-mock",
        },
        {
            "event": "paid_read",
            "article_id": 3,
            "creator": "Alice Chen",
            "amount_usdc": 0.001,
            "tx_hash": "0x" + "c" * 64,
            "transaction_id": "old-unknown",
            "buyer": "buyer-legacy",
        },
    ]
    run_log = tmp_path / "usage.jsonl"
    run_log.write_text(
        "\n".join(json.dumps(event) for event in events),
        encoding="utf-8",
    )
    monkeypatch.setattr(restore_usage_log, "RUN_LOG", run_log)
    monkeypatch.setattr(
        restore_usage_log,
        "CREATOR_WALLETS",
        tmp_path / "missing-creator-wallets.json",
    )
    monkeypatch.setattr(restore_usage_log, "BACKUP_DIR", tmp_path / "backups")

    result = restore_usage_log.restore()

    assert result["inserted_receipts"] == 3
    assert _receipt_modes("usage-sim") == ["live", "mock", "legacy"]

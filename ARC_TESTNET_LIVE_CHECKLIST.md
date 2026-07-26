# Arc Testnet live settlement checklist

Obol supports both deterministic mock receipts for local development and live
USDC transfers through Circle Wallets on Arc Testnet. Final-submission evidence
must be generated specifically for this repository; do not reuse wallet IDs,
transaction IDs, or screenshots from an earlier competition entry.

## Configure locally

Create `backend/.env`:

```env
CIRCLE_API_KEY=...
CIRCLE_ENTITY_SECRET=...
CIRCLE_AGENT_WALLET_ID=...
ARC_USDC_TOKEN_ID=...
ARC_USDC_TOKEN_ADDRESS=0x3600000000000000000000000000000000000000
FLASK_DEBUG=0
OBOL_AUTO_SEED=1
```

Never commit this file or paste its values into documentation, chat, issues, or
screenshots.

## Check readiness

```bash
cd backend
python app.py
```

Open `http://localhost:5001/api/settlement/status`. A live-ready environment
should report:

```json
{
  "mode": "live",
  "blockchain": "ARC-TESTNET",
  "ready_for_live_transfers": true,
  "missing": []
}
```

## Generate fresh evidence

1. Create or select a dedicated evaluation wallet for this iteration.
2. Fund it with Arc Testnet USDC from the Circle faucet.
3. Run an agent query with a small budget.
4. Confirm the response reports `settlement_mode: "live"`.
5. Verify the receipt contains a Circle transaction ID and an Arc transaction
   hash.
6. Verify that hash with an Arc Testnet explorer.
7. Record only the minimum public evidence needed for judging. Do not publish
   the Circle wallet ID, API key, entity secret, or recovery material.
8. Label every transfer and seeded metric as testnet evaluation activity.

## Safety

- Keep `OBOL_FORCE_MOCK=1` during automated tests and persona evaluation.
- Do not commit `backend/.env`, databases, wallet pools, logs, or recovery files.
- Use very small testnet amounts.
- Never claim seeded or evaluator-generated activity as organic traction.
- If live settlement is unavailable, describe the mock/live boundary honestly.


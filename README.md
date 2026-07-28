# Obol — *programmable pay-per-read for AI agents*

**Arc Programmable Money Hackathon · Agentic Economy track**

[**Live judge demo → obol-programmable-money.onrender.com**](https://obol-programmable-money.onrender.com)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/xiangchengzilema/obol-programmable-money)

Obol gives autonomous AI agents a USDC budget to buy creator content per read,
settle through Circle Wallets on Arc, and produce a receipt for every buy,
reuse, skip, or stop decision.

## Competition iteration

Obol was originally created for the Lepton Agents Hackathon. This repository is
an openly disclosed, independently maintained continuation for the Arc
Programmable Money Hackathon. The original Lepton submission remains frozen so
its ongoing judging is unaffected. This repository started from the submitted
source snapshot at
[`xiangchengzilema/obol@681996c`](https://github.com/xiangchengzilema/obol/commit/681996c8efc31598f0e9a3d3c3d3d5aafec7d845).

This iteration focuses on programmable spending policies, clearer agent
accountability, stronger Circle/Arc integration, a stable public demo, and
refreshed evaluation evidence. It is not presented as a project started from
scratch during this hackathon.

AI agents are reading the internet. Today they pay creators nothing. **Obol** flips
that: creators put articles behind a one-cent **nanopaywall**, and an autonomous
research agent **decides** what's worth reading, **pays per article in USDC on Arc**,
and returns an answer with a **receipt for every cent** - so creators earn each time
an AI reads them.

### How it works
1. **Creators** list an article and set a per-read price (e.g. $0.01).
2. You ask the **agent** a question with a USDC budget and programmable
   guardrails.
3. The agent scores each article, **buys the ones worth paying for within budget,
   reuses prior purchases, skips the rest (with reasons), and stops when its
   policy says enough evidence has been collected**.
4. You get an answer with citations; creators see earnings tick up in real time.

The agent's **buy/reuse/skip/stop audit log** is the heart of it — real agency,
not a scripted checkout.

### Programmable spending policy

Every run can carry its own deterministic USDC policy:

- `reserve_usdc`: balance that must remain unspent
- `max_price_usdc`: maximum price for one source
- `min_relevance`: minimum usefulness score
- `max_purchases`: maximum number of new paid reads
- `coverage_target`: stop once the query is sufficiently covered

Obol snapshots that policy with the run. Every decision records the stable rule
that fired, its explanation, and the budget before and after the action. A final
`stop` event explains why the agent ended the spending loop.

### How AI agents integrate

The website buttons are demo controls for judges. The agent-facing product surface
is HTTP:

1. **Native Obol agent API**: an app or AI workflow calls `POST /api/agent/run`
   with a query and USDC budget. Obol ranks sources, pays selected creators through
   Circle Wallets on Arc Testnet, and returns an answer plus receipts.
2. **x402 machine-payable endpoint**: an external agent calls
   `GET /x402/articles/:id`. If unpaid, it receives HTTP 402 with price, asset,
   pay-to address, resource id, and nonce. After paying, it retries with
   `X-Payment` and receives the full content plus a resource-bound receipt.
3. **Human unlock**: `POST /api/articles/:id/unlock` exists so a judge can click
   through the same settlement flow in the browser. It is a visual demo path, not
   the only way to use Obol.

Minimal agent call:

```bash
curl -X POST http://localhost:5001/api/agent/run \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"Arc testnet predictable fees for AI paid reads\",\"budget_usdc\":0.05,\"policy\":{\"reserve_usdc\":0.005,\"max_price_usdc\":0.02,\"min_relevance\":0.35,\"max_purchases\":2}}"
```

Minimal x402 flow:

```bash
curl -i http://localhost:5001/x402/articles/1
curl http://localhost:5001/x402/articles/1 \
  -H "X-Payer: external-research-agent" \
  -H "X-Payment: 0xabc123paidproof"
```

### Why Arc
Per-article payments only make sense when fees are tiny and predictable. Arc settles
in USDC with sub-second finality and ~$0.01 fees, so paying $0.002 to read an article
nets out positive.

### Stack
- **Backend** (`backend/`): Python + Flask, SQLite. Autonomous decision engine,
  Circle wallet settlement (live + mock), optional LLM.
- **Frontend** (`frontend/`): marketplace, agent console, creator dashboard.
- **Settlement**: Circle on Arc Testnet (USDC nanopayments).

### Run
```bash
# option A: one-service demo (recommended for deployment)
cd backend
pip install -r requirements.txt
python app.py   # open http://localhost:5001

# option B: frontend dev server (optional)
cd frontend
python -m http.server 5500   # http://localhost:5500
```
Runs with zero config in mock mode. Add `OPENAI_API_KEY` for smarter decisions.
When `CIRCLE_API_KEY`, `CIRCLE_ENTITY_SECRET`, and `CIRCLE_AGENT_WALLET_ID` are
present, Obol uses live Circle Wallets on Arc Testnet.

The earlier Obol iteration completed live agent payments on Arc Testnet. This
iteration will publish refreshed, independently reproducible testnet evidence
before final submission. All seeded activity and testnet transfers are labelled
as **demo/evaluation data**, not organic traction.

Check readiness at `/api/settlement/status`; see `ARC_TESTNET_LIVE_CHECKLIST.md`.

Deployment uses a single process:

```bash
gunicorn --chdir backend --workers 1 --threads 4 --timeout 120 \
  --bind 0.0.0.0:$PORT wsgi:app
```

The Flask app serves both `/api/*` and the static frontend. The public WSGI
entrypoint is fail-closed: it defaults to mock settlement and disables reset so
an anonymous judge-facing deployment cannot access Circle wallet credentials.
Real Arc Testnet evidence is generated locally and shared only as non-secret
transaction proof. See `DEPLOYMENT.md`.

### Demo flow
Open `http://localhost:5001`, run the Agent Console, then visit Creator Studio
and x402. The demo reset button reseeds the local database so recordings start
with fresh buy receipts instead of cache reuses. In live mode, reset requires an
extra confirmation if local live receipts already exist.

### 5-persona evaluation

```bash
cd backend
python persona_eval.py
```

This generates `media/persona_evaluation_report.md` with a local QA/traction run
covering creator publishing, autonomous agent purchases, x402 unlocks, receipts,
and cache reuse.
The UI labels this as demo/evaluation activity; it is not presented as organic
user traction.

### Demo revenue / creator wallet evidence

To reproduce the current creator revenue setup:

```bash
cd backend
python demo_revenue.py --dry-run
python demo_revenue.py --live --create-creator-wallets
```

`--create-creator-wallets` replaces obvious seed placeholder addresses with
distinct Circle payout wallets. `--live` spends Arc testnet USDC from the funded
agent wallet and records receipts with `source=evaluation-agent`.

### Verify

```bash
cd backend && python -m pytest -q test_obol.py -p no:cacheprovider
cd .. && node --check frontend/app.js
```

Current result: **26 backend tests passing**, plus JavaScript syntax validation.

See `PROGRAMMABLE_MONEY_SUBMISSION.md` for checkpoint copy,
`FINAL_SUBMISSION_DRAFT.md` for the final form/video/deck source, and
`ARC_ITERATION_CHANGELOG.md` for a transparent inherited-vs-new breakdown. The
backend routes live in `backend/app.py`; the machine-payment flow lives in
`backend/x402.py`.



# Obol deployment notes

## Recommended shape
Use one Python web service. The Flask app serves:

- `/` and frontend assets from `frontend/`
- `/api/*` backend JSON APIs
- `/x402/articles/<id>` machine-payable content endpoint

## Railway / Render style start command

```bash
cd backend && python app.py
```

The app reads `PORT` automatically. If no `PORT` is set, it uses `FLASK_PORT`
or `5001`.

## Environment variables

Required for mock demo: none.

Recommended:

```env
OBOL_AUTO_SEED=1
OBOL_DISABLE_DEMO_RESET=0
FLASK_DEBUG=0
```

Optional:

```env
OPENAI_API_KEY=
OBOL_LLM_MODEL=gpt-4o-mini
CIRCLE_API_KEY=
CIRCLE_ENTITY_SECRET=
CIRCLE_AGENT_WALLET_ID=
ARC_USDC_TOKEN_ID=15dc2b5d-0994-58b0-bf8c-3a0501148ee8
```

For a public judging link, keep mock mode acceptable until Circle testnet
credentials are ready. If live Circle credentials are configured, install
`cryptography` and uncomment it in `backend/requirements.txt`.

## Demo reset

`POST /api/demo/reset` reseeds creators/articles and clears runs/receipts. It is
useful for repeated recordings. Disable it with:

```env
OBOL_DISABLE_DEMO_RESET=1
```

## Verification

```bash
cd backend
D:\python\python.exe -m pytest test_obol.py -q

cd ..
node --check frontend/app.js
```

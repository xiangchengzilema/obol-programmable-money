# Circle live setup helper

Official-docs-based helper scripts for registering a Circle entity secret and
creating an Arc Testnet developer-controlled wallet.

Run from this directory:

```bash
npm install
npm run register-entity-secret
npm run create-wallet
npm run check-wallet
```

Local outputs:

- `backend/.env` receives `CIRCLE_ENTITY_SECRET` and
  `CIRCLE_AGENT_WALLET_ID`.
- `tools/circle-live-setup/recovery/` stores Circle recovery material.

Both locations are ignored by Git. Never commit, print, paste, or publish their
contents. Use a dedicated Arc Testnet evaluation wallet for this competition
iteration, fund it through `https://faucet.circle.com/`, and expose only the Arc
transaction hash required for public verification.


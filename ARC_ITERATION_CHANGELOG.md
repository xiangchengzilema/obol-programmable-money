# Arc iteration changelog

This file separates inherited Obol functionality from work completed for the
Arc Programmable Money Hackathon.

## Starting point

- Frozen prior submission:
  [`xiangchengzilema/obol@681996c`](https://github.com/xiangchengzilema/obol/commit/681996c8efc31598f0e9a3d3c3d3d5aafec7d845)
- New isolated repository:
  `xiangchengzilema/obol-programmable-money`
- Checkpoint 2 submitted: 27 July 2026

The starting snapshot already included the Flask/web MVP, buy/reuse/skip
research-agent loop, Circle Wallets integration, Arc Testnet receipt fields, a
native agent API, and an x402-style endpoint.

## Work completed in this repository

### Programmable spending policy

- Request-scoped reserve, per-source price cap, minimum relevance, maximum
  purchase count, and coverage target.
- Immutable policy snapshot stored with each run.
- Stable policy-rule identifiers and before/after budget values stored for each
  decision.
- Explicit stop event and reason returned in the audit log.
- Browser controls and policy-audit view for the judge demo.

### Deployment and public-demo safety

- Railway configuration as code.
- Production Gunicorn WSGI entrypoint.
- Public deployment defaults to mock settlement and disables database reset,
  preventing an anonymous judge-facing service from receiving Circle wallet
  credentials accidentally.
- Optional persistent SQLite volume configuration documented.

### Submission evidence

- Competition-specific final submission draft.
- Three-minute video script and seven-slide deck outline.
- Honest evidence rules: seeded records, automated evaluation, mock receipts,
  and Arc Testnet transfers are never described as organic users or production
  revenue.

## Evidence still to complete

- Public HTTPS demo and incognito smoke test.
- Fresh local Circle Wallets transfer on Arc Testnet.
- Public Arc explorer proof.
- Final test count and commit SHA.
- Final deck PDF and public three-minute video.

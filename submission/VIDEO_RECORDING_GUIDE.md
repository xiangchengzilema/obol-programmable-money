# Obol — 3-Minute Demo Recording Guide

Use this guide to record the final public demo video. The target runtime is
**2:50–2:58**. Record in English at 1080p and keep the browser zoom around
90–100%.

## Before recording

1. Open <https://obol-programmable-money.onrender.com>.
2. Wait up to one minute if the free Render service is waking.
3. Close personal tabs and hide the bookmarks bar.
4. Confirm the page says **Public demo / Mock settlement**. This is intentional:
   the interactive run stays simulated, while the separate **Fresh evidence**
   panel exposes the independently verified Arc Testnet payment.
5. Prepare these two public links in a text file:
   - Demo: <https://obol-programmable-money.onrender.com>
   - Code: <https://github.com/xiangchengzilema/obol-programmable-money>
6. Do one silent rehearsal. For the actual take, refresh the site and record the
   first clean run after a fresh deployment.

## Exact recording sequence

| Time | What to show and click | Narration |
|---|---|---|
| 0:00–0:15 | Start on the Obol hero. Keep “Agent reads. Creator gets paid. Arc proves it.” and the mock-mode label visible. | “AI agents read valuable human research every day, but creators are rarely paid. Obol lets an autonomous agent buy content one read at a time in USDC, while explaining every cent it spends.” |
| 0:15–0:32 | Briefly scroll through the marketplace cards and their per-read prices. Then click **Agent Console**. | “Subscriptions are too coarse for software, and manual checkout breaks autonomous workflows. In Obol, creators set a small price, while the agent receives a question and a hard spending budget.” |
| 0:32–0:48 | In **Agent Console**, enter the query below, set the budget to `0.05`, leave the displayed policy controls at reserve `0.005`, maximum price `0.02`, minimum relevance `0.35`, and maximum purchases `2`. | “This request has a five-cent budget, a protected reserve, a per-source price cap, and explicit relevance and purchase limits. Those constraints become part of the agent’s reasoning.” |
| 0:48–1:12 | Click **Run agent**. Let the animation finish. Show the result summary, budget kept, answer, and decision table. | “The agent ranks previews by relevance, price, redundancy, prior authorization, and coverage. It can buy, reuse, skip, or stop. In this run, it selected one useful source, preserved the rest of the budget, and recorded why every other candidate was skipped.” |
| 1:12–1:37 | Slowly scroll through the decision audit. Pause on at least one **buy**, one **skip**, and the final **stop** row. | “This trace is the core of Obol. Payment is not a scripted final step; the spending constraint changes the research plan. Every row records the rule that fired and the balance before and after the decision.” |
| 1:37–1:57 | Show the receipt and settlement-mode label. If the run displays `$0.010 spent`, `$0.040 remaining`, and `$0.005 reserve`, keep them visible. If the numbers differ, describe the numbers actually shown. | “The submitted public demo is deliberately running in clearly labelled mock mode, so no secret wallet credentials are exposed. The receipt schema still records the creator, article, amount, decision rationale, and settlement mode. We do not present mock hashes as on-chain proof.” |
| 1:57–2:25 | Click **x402**. Choose an article, click **Get 402 challenge**, pause on the HTTP 402 response, then click **Pay and unlock** and pause on the returned content and receipt. | “Other agents do not need this website. They can call the native agent API, or use this x402-style flow. An unpaid request receives a machine-readable HTTP 402 challenge; an authorized retry receives the content and a resource-bound receipt.” |
| 2:25–2:48 | Return to the home page, pause on **Fresh evidence**, and click **Verify again**. Keep the strict-match status, Arc block, transaction hash, and Arcscan button visible. | “The anonymous playground never receives wallet secrets, but this separate evidence panel binds the submitted run to a real completed Arc Testnet USDC transfer. The server verifies the transaction hash, payer, token contract, recipient, amount, and block. Forty-six backend tests pass.” |
| 2:48–2:58 | Return to the hero or show slide 7 with the demo and repository URLs. | “Obol makes every paid AI read intentional, inspectable, and creator-aligned. It is programmable money inside the agent’s reasoning loop.” |

## Prepared Agent Console values

Paste this query:

```text
Arc testnet predictable fees for AI paid reads
```

Use:

```text
Budget: 0.05 USDC
Reserve: 0.005 USDC
Maximum source price: 0.02 USDC
Minimum relevance: 0.35
Maximum purchases: 2
```

The verified evaluation run produced one `$0.010` purchase, `$0.040` remaining,
and a `$0.005` protected reserve. If the recording run produces a reuse or
different numbers because the public demo has already been exercised, narrate
the values actually visible on screen.

## Upload and verification

1. Export the video at 1080p, H.264.
2. Confirm the final duration is no longer than 3:00.
3. Upload to YouTube as **Unlisted** or to Loom with public viewing enabled.
4. Open the video link in an incognito window and verify it plays without login.
5. Paste the public video URL into the Encode final-submission form.

Do not show browser account names, Render settings, Circle credentials, GitHub
tokens, `.env` files, or wallet recovery material.

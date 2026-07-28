# Obol — Arc Programmable Money Hackathon Final Submission Draft

> Working document for the final submission. Do not paste any text containing
> `[FINAL: ...]` into the form. Replace every placeholder with verified evidence
> from this repository before the Beijing deadline of **10 August 2026, 19:59**.
>
> Evidence rule: seeded records, persona runs, automated usage simulations, mock
> receipts, and testnet transfers are demo/evaluation activity. They must never
> be described as organic users, production volume, or real creator revenue.

## 1. Paste-ready final form fields

### Project name

Obol — Programmable Pay-per-Read for AI Agents

### Track

Agentic Economy

### One-liner

Obol gives autonomous AI agents a USDC budget to buy creator content per read,
settle through Circle Wallets on Arc, and produce an auditable receipt for every
buy, reuse, skip, or stop decision.

### Short description

Obol is a programmable pay-per-read layer for the agentic economy. A research
agent receives a query and a USDC budget, evaluates paywalled sources, and
decides whether to buy, reuse, skip, or stop. Purchases can settle through
Circle Wallets on Arc Testnet, while a decision trace and receipt ledger explain
why money moved. External agents can integrate through a native API or an
x402-style HTTP 402 flow.

### Full project description

AI agents increasingly consume human-written research, but creators rarely
receive compensation when their work is used. Obol turns access to each article
into a machine-readable, pay-per-read decision.

A creator publishes an article with a small USDC price. A research agent receives
a question and a maximum budget, then evaluates candidate previews using
relevance, price, redundancy, prior authorization, coverage, and remaining
budget. For each source it chooses one of four accountable actions: buy it,
reuse a previously purchased source at no additional cost, skip it with a
reason, or stop spending once it has enough coverage. The final answer is built
only from purchased or previously authorized content.

When live credentials are configured, Obol uses Circle Wallets to settle USDC
on Arc Testnet. Its ledger ties each paid read to the article, creator, amount,
decision rationale, Circle transaction ID, and Arc transaction hash. The
product also exposes `POST /api/agent/run` for agent workflows and an x402-style
`GET /x402/articles/:id` challenge-and-retry interface for machine-native paid
access.

Obol was originally created for the Lepton Agents Hackathon. This Arc entry is
an openly disclosed continuation in a separate repository, not a project
presented as new from scratch. The original Lepton submission remains frozen.
For this hackathon, we focused on `[FINAL: list only verified new work completed
in this repository]`.

The result is a concrete agentic-money loop: a spending constraint changes the
agent's reasoning, the agent decides whether value justifies payment, and every
movement of money can be inspected afterward.

### Problem

AI agents can retrieve and synthesize content at scale, but today's access
models offer neither a practical per-read payment rail for creators nor an
auditable explanation of why an autonomous agent spent money. Subscriptions are
too coarse for agents, manual checkout breaks automation, and opaque agent
spending is difficult to trust.

### Solution

Obol combines tiny USDC paywalls, a budget-conscious research agent, Circle
Wallets settlement on Arc Testnet, and a receipt ledger. It lets software decide
which source is worth paying for while keeping the budget, rationale, content
authorization, and payment proof visible.

### How Arc and Circle are used

- Circle Wallets provides the programmable USDC wallet and transfer layer.
- Arc Testnet is the settlement network recorded on paid-read receipts.
- Each live receipt can include a Circle transaction ID and Arc transaction
  hash.
- `GET /api/settlement/status` exposes non-secret readiness and clearly labels
  the current mode as `mock` or `live`.
- Automated tests and local evaluation run in mock mode; only independently
  verified transfers from this iteration should be presented as live testnet
  evidence.

### Agentic Economy track fit

Obol is not a chatbot wrapper or a scripted checkout. Money is an input to the
agent's reasoning loop.

- **Inputs:** a query, a USDC budget, source previews, prices, prior purchases,
  and current coverage.
- **Decisions:** buy, reuse, skip, or stop.
- **Constraints:** never exceed budget; do not buy redundant or low-value
  sources; preserve unused budget when sufficient evidence has been acquired.
- **Execution:** settle approved purchases through Circle Wallets on Arc
  Testnet when live mode is enabled.
- **Accountability:** record the reason, amount, content authorization, Circle
  transaction ID, and Arc transaction hash.
- **Machine interface:** expose both a native agent API and an x402-style HTTP
  402 flow.

This makes programmable money part of autonomous judgment rather than a payment
button added after the decision.

### Technical implementation

- Python and Flask backend
- SQLite decision, authorization, and receipt ledger
- Budget-aware research agent with buy/reuse/skip/stop behavior
- Heuristic scoring by default, with optional LLM-assisted scoring
- Circle developer-controlled wallet integration with explicit mock/live modes
- Arc Testnet USDC settlement path
- Native agent API and x402-style HTTP 402 endpoint
- Responsive browser interface for the marketplace, agent console, receipts,
  and creator earnings
- Repeatable automated tests and evaluation utilities

### Repository

https://github.com/xiangchengzilema/obol-programmable-money

### Public demo

https://obol-programmable-money.onrender.com

Verified without credentials on 2026-07-28 at 12:32 (Asia/Shanghai). The free
Render instance may take up to a minute to wake after a period of inactivity.

### Pitch/demo video

`[FINAL: public YouTube/Loom link; verify no login is required and runtime is at
or below three minutes]`

### Presentation deck

`[FINAL: public Google Slides/Canva/PDF link; enable “anyone with the link can
view”]`

### Link access instructions

All submission links are public and require no credentials. The demo opens with
seeded evaluation content so judges can test the agent flow safely. Any
testnet/evaluation metrics shown in the interface are labelled as such.

### Team

Solo builder — `[FINAL: confirm the public name to display]`

## 2. Existing-project disclosure

Use this wherever the form asks whether the project existed before the
hackathon:

> Obol was first built and submitted for the Lepton Agents Hackathon. We are
> openly continuing that work for the Arc Programmable Money Hackathon in a
> separate repository. The original Lepton submission remains frozen, and this
> entry is not presented as a project started from scratch. Our final
> submission distinguishes the inherited baseline from the work completed
> during this hackathon.

Original frozen source snapshot:

https://github.com/xiangchengzilema/obol/commit/681996c8efc31598f0e9a3d3c3d3d5aafec7d845

### Inherited baseline

The starting snapshot already contained the core Flask/web MVP, the budgeted
research-agent concept, buy/reuse/skip decisions, receipt views, Circle/Arc
settlement support, a native agent endpoint, and an x402-style endpoint.

### New work completed during this Arc iteration

Replace the placeholders below from the final Git diff and evidence log. Do not
claim planned work as completed work.

- Request-scoped protected reserve, per-source price cap, minimum relevance,
  maximum purchase count, and coverage target.
- Immutable policy snapshots plus rule IDs, before/after balances, and an
  explicit final stop event in every run audit.
- A public-demo WSGI safety boundary that defaults anonymous deployments to
  mock settlement and refuses unverified x402 proofs in live mode.
- Render and Railway configuration, a production Gunicorn entrypoint, health
  check, and documented deployment persistence trade-offs.
- Browser policy controls and a judge-readable policy audit panel.
- **26 backend tests passing** with
  `python -m pytest -q test_obol.py -p no:cacheprovider`, plus a successful
  `node --check frontend/app.js`.
- `[FINAL: fresh Arc Testnet evidence generated specifically for this repo,
  including a public explorer link if available]`
- `[FINAL: new evaluation result, explicitly labelled demo/evaluation rather
  than user traction]`
- `[FINAL: competition-specific deck and three-minute video]`

### Paste-ready “what changed” paragraph

> Obol entered this hackathon with an existing MVP from the Lepton Agents
> Hackathon. In the separate Arc iteration, we added request-scoped spending
> guardrails, immutable policy and stop audits, browser policy controls, and a
> fail-closed public-demo deployment path. We also published
> https://obol-programmable-money.onrender.com and verified the build with 26 backend tests
> plus a JavaScript syntax check. Any seeded usage, automated
> evaluation, and testnet transfers shown in the demo are labelled as
> evaluation activity, not organic traction.

## 3. Evidence table to complete before submission

| Claim | Evidence required | Final value |
|---|---|---|
| Public demo works | Logged-out HTTP smoke test | `https://obol-programmable-money.onrender.com — HTTP 200 verified 2026-07-28 12:32 Asia/Shanghai` |
| Repository is public | Logged-out GitHub check | `https://github.com/xiangchengzilema/obol-programmable-money` |
| Tests pass | Fresh terminal output | `26 passed; final commit SHA pending` |
| Frontend parses | Fresh `node --check` output | `Passed; final commit SHA pending` |
| Settlement mode is explicit | `/api/settlement/status` screenshot/JSON | `mock; force_mock=true; ready_for_live_transfers=false` |
| Fresh Circle transfer exists | Circle transaction status | `[FINAL: transaction ID, redact non-public wallet metadata]` |
| Fresh Arc proof exists | Public Arc Testnet explorer | `[FINAL: tx URL/hash]` |
| Agent respects budget | Demo response and/or test | `$0.050 budget; $0.010 spent; $0.040 remaining; $0.005 protected reserve` |
| Agent makes accountable choices | Decision trace | `One buy plus explicit redundant_coverage, min_relevance, and candidate_scan_complete decisions` |
| x402 flow works | 402 response followed by authorized 200 | `Verified on public demo 2026-07-28; demo receipt is mock-labelled and persisted=false` |
| Video is public | Logged-out playback | `[FINAL: URL and exact duration]` |
| Deck is public | Logged-out view | `[FINAL: URL]` |

If fresh live settlement is not available, remove any statement that suggests a
live transfer was completed in this iteration. State instead that the product
implements a Circle/Arc live path, while the submitted demo is running in
clearly labelled mock mode.

## 4. Three-minute pitch/demo video script

Target runtime: **2:50–2:58**, leaving a small upload/playback margin. Record at
1080p, enlarge important text, hide secrets and personal browser tabs, and use
fresh demo data. Bracketed proof must be replaced before recording.

### 0:00–0:15 — Hook

**Show:** Obol hero and the line “Agent reads. Creator gets paid. Arc proves it.”

**Say:**

> AI agents read valuable human research every day, but creators are rarely
> paid. Obol lets an autonomous agent buy content one read at a time in USDC,
> while explaining every cent it spends.

### 0:15–0:35 — Problem and product

**Show:** Creator articles with visible per-read prices, then the Agent Console.

**Say:**

> Subscriptions are too coarse for software, and manual checkout breaks
> autonomous workflows. In Obol, creators set a small price, while the agent
> receives a question and a hard spending budget.

### 0:35–1:10 — Run the agent

**Show:** Enter a prepared query and a small budget; click Run. Keep the input,
budget, and result visible.

**Say:**

> The agent evaluates preview relevance, price, redundancy, prior purchases,
> current coverage, and remaining budget. It can buy a useful source, reuse an
> authorized source for free, skip a weak or unaffordable one, or stop when it
> has enough evidence. Here, it spent `[FINAL: amount]` from a `[FINAL: budget]`
> budget and left `[FINAL: remainder]` unspent.

### 1:10–1:40 — Explain the decision trace

**Show:** One purchased source and at least one skip, reuse, or stop reason.

**Say:**

> This trace is the core of Obol. Payment is not a scripted final step; the
> spending constraint changes the research plan. The answer is synthesized only
> from content the agent purchased or was already authorized to reuse.

### 1:40–2:05 — Circle and Arc proof

**Show:** Receipt ledger, Circle transaction ID, Arc transaction hash, then the
public explorer if fresh live proof is available.

**Say (live-evidence version):**

> This evaluation purchase settled through Circle Wallets on Arc Testnet. The
> receipt records the creator, article, amount, rationale, Circle transaction
> ID, and Arc transaction hash. This is testnet evaluation activity, not
> production revenue or organic usage.

**Say (mock-demo fallback):**

> This public demo is running in clearly labelled mock mode. The same receipt
> schema and Circle integration support live Arc Testnet settlement, but we do
> not present mock hashes as onchain proof.

### 2:05–2:30 — Machine-to-machine access

**Show:** A compact terminal capture or x402 screen: first request returns HTTP
402; retry with payment proof returns the article and receipt.

**Say:**

> Other agents do not need to use this website. They can call the native agent
> API, or request an article through an x402-style endpoint. An unpaid request
> receives a machine-readable HTTP 402 challenge; an authorized retry receives
> the content and a resource-bound receipt.

### 2:30–2:48 — What was built in this hackathon

**Show:** A clean slide with four verified improvements and the Arc repository
URL.

**Say:**

> Obol began in an earlier hackathon, and we disclose that openly. For this Arc
> iteration we added `[FINAL: verified improvement 1]`, `[FINAL: improvement
> 2]`, `[FINAL: improvement 3]`, and `[FINAL: improvement 4]` in a separate
> repository.

### 2:48–2:58 — Close

**Show:** Hero, project name, track, repository, and demo URL.

**Say:**

> Obol makes every paid AI read intentional, inspectable, and creator-aligned.
> It is programmable money inside the agent's reasoning loop.

## 5. Seven-slide deck outline

Keep each slide to one headline, one visual idea, and at most three short proof
points. Use screenshots from the final build rather than generic AI artwork.

### Slide 1 — Obol

**Headline:** Agent reads. Creator gets paid. Arc proves it.

**Visual:** Final product hero with project, track, repository, and demo URL.

**Message:** Programmable pay-per-read for autonomous AI agents.

### Slide 2 — The missing payment layer for AI research

**Headline:** Agents consume value, but creators do not get paid per use.

**Visual:** Current flow (agent reads / creator earns nothing) versus Obol flow
(agent decides / USDC settles / receipt proves).

**Proof points:** subscriptions are coarse; manual checkout blocks agents;
opaque spending is difficult to audit.

### Slide 3 — One query, one budget, four accountable actions

**Headline:** Buy, reuse, skip, or stop.

**Visual:** Screenshot of the final Agent Console and decision trace.

**Proof points:** hard budget; coverage-aware stopping; answers use only
authorized content.

### Slide 4 — Programmable money is part of the reasoning

**Headline:** Price and budget change what the agent does.

**Visual:** Decision loop:
query + budget + previews → score → buy/reuse/skip/stop → answer + receipts.

**Proof points:** relevance; redundancy; remaining budget/accountability.

### Slide 5 — Circle Wallets on Arc

**Headline:** Settlement and proof for every paid read.

**Visual:** Architecture:
external agent/browser → Obol API/x402 → decision engine → Circle Wallets →
Arc Testnet → receipt ledger.

**Proof points:** explicit mock/live mode; Circle transaction ID; Arc
transaction hash.

### Slide 6 — Working MVP and honest evidence

**Headline:** A reproducible product, not a simulated pitch.

**Visual:** Three final screenshots: agent run, ledger/explorer proof, x402
challenge-and-retry.

**Proof points:** `[FINAL: exact tests]`; `[FINAL: public demo]`; `[FINAL: fresh
testnet evidence or clearly labelled mock fallback]`.

Footer: “Seeded usage, automated evaluation, and testnet transfers are not
organic traction.”

### Slide 7 — This Arc iteration

**Headline:** From existing MVP to Arc-ready programmable spending.

**Visual:** Two columns: inherited baseline versus verified work completed in
this hackathon.

**Proof points:** `[FINAL: improvement 1]`; `[FINAL: improvement 2]`; `[FINAL:
improvement 3]`.

Close with repository, demo, video, and “Agentic Economy.”

## 6. Final submission checklist

### Product and code

- [ ] Work only in `obol-programmable-money`; the frozen Lepton repository is
  unchanged.
- [ ] Confirm the repository is public and the final commit is pushed to `main`.
- [ ] Run the complete backend test command and record the exact pass count.
- [ ] Run `node --check frontend/app.js`.
- [ ] Test `/api/health`, `/api/settlement/status`, `/api/agent/run`,
  `/api/ledger`, and the x402 402→200 flow.
- [ ] Confirm the agent never exceeds budget and can visibly skip or stop.
- [ ] Confirm answers use only purchased or previously authorized sources.
- [ ] Verify mobile and small-laptop layouts sufficiently for judges.

### Security and privacy

- [ ] Run the required pre-push secret scan:
  `rg -n "ghp_|API_KEY=.{10}" -g "*.py" .`
- [ ] Check the entire Git diff for API keys, tokens, entity secrets, wallet
  recovery data, `.env` files, databases, and logs.
- [ ] Revoke any GitHub token that was pasted into chat or another unsafe
  location.
- [ ] Hide browser bookmarks, account names, API dashboards, and secrets in the
  recording.

### Deployment

- [ ] Deploy one stable HTTPS service and set production-safe environment
  variables.
- [ ] Disable or protect destructive demo reset behavior as appropriate.
- [ ] Open the demo in an incognito/logged-out browser.
- [ ] Run the complete judge flow from a clean state.
- [ ] Verify the host does not sleep, crash, or lose required demo state during
  the judging window.
- [ ] Add a clear mock/live label that matches `/api/settlement/status`.

### Circle and Arc evidence

- [ ] Use credentials and evidence generated specifically for this repository.
- [ ] If live mode is ready, make only a very small Arc Testnet USDC evaluation
  transfer.
- [ ] Confirm Circle reports a transaction ID and finalized state.
- [ ] Confirm the Arc transaction hash on a public testnet explorer.
- [ ] Capture only non-secret evidence.
- [ ] Label transfers as testnet evaluation activity.
- [ ] If live proof is unavailable, use the honest mock-demo fallback language.

### Submission copy and disclosure

- [ ] Replace every `[FINAL: ...]` placeholder in this document.
- [ ] Compare the final branch with the frozen Lepton snapshot and list only
  work actually completed during this hackathon.
- [ ] Include the existing-project disclosure in the form, deck, and video.
- [ ] Do not claim seeded creators, persona runs, automated traffic, testnet
  transfers, or mock receipts as organic traction.
- [ ] Do not claim a partnership, endorsement, mainnet deployment, or production
  usage unless independently verified.
- [ ] Make repository, demo, deck, and video links public with no login.

### Three-minute video

- [ ] Record from the final deployed commit, not a different local state.
- [ ] Show the budget, at least two decision types, answer, ledger, and x402
  flow.
- [ ] Show fresh Arc explorer proof only if it is genuinely live testnet proof.
- [ ] State the existing-project disclosure and this iteration's verified work.
- [ ] Keep runtime at or below 3:00; target 2:50–2:58.
- [ ] Check voice clarity, cursor visibility, text size, and 1080p playback.
- [ ] Verify the public link in an incognito browser.

### Seven-slide deck

- [ ] Use the final screenshots and the same facts as the form/video.
- [ ] Keep the existing-versus-new comparison explicit.
- [ ] Include repository and demo links on the first and last slides.
- [ ] Export a PDF backup.
- [ ] Verify public access without a Google/Canva login.

### Final platform submission

- [ ] Open the Encode project page and wait for the final-submission stage/button
  to become available.
- [ ] Paste the final repository, demo, presentation, and video links.
- [ ] Select only **Agentic Economy Track**, unless the final product genuinely
  satisfies another track's requirements.
- [ ] Re-open every pasted URL before submitting.
- [ ] Review the final preview for missing fields or truncated text.
- [ ] Submit before **10 August 2026, 19:59 Beijing time**; do not wait for the
  final hour.
- [ ] Save a screenshot of the success confirmation and “View/Edit Submission”
  state.

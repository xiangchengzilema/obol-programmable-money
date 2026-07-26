# Arc Programmable Money Hackathon — submission draft

This file is the paste-ready source for the Encode project page and checkpoints.
It deliberately discloses Obol's earlier Lepton submission and labels testnet
evaluation activity honestly.

## Project name

Obol — Programmable Pay-per-Read for AI Agents

## One-liner

Obol gives autonomous AI agents a USDC budget to buy creator content per read,
settle through Circle Wallets on Arc, and produce a receipt for every decision.

## Track

Agentic Economy

## Project description

Obol is a programmable pay-per-read layer for the agentic economy. AI agents
increasingly consume human-written research, but creators rarely receive
compensation. With Obol, creators publish content behind tiny USDC nanopaywalls.
A research agent receives a query and a spending budget, evaluates previews,
price, relevance, redundancy, and coverage, then autonomously chooses to buy,
reuse, or skip each source. It can stop early and leave budget unspent when
additional purchases add little value.

For every purchase, Obol settles USDC through Circle Wallets on Arc Testnet and
records an auditable receipt containing the creator, article, amount, decision
rationale, Circle transaction ID, and Arc transaction hash. The resulting
answer cites only purchased or previously authorized sources. External agents
can also use Obol through a native API or an x402-style HTTP 402
challenge-and-retry flow.

Obol was originally created for the Lepton Agents Hackathon. For the Arc
Programmable Money Hackathon, we are continuing it as a clearly separated
iteration rather than presenting it as a new-from-scratch project. This version
focuses on programmable budget policies, clearer agent accountability, stronger
Circle/Arc integration, a stable public demo, and updated evaluation evidence.
The goal is simple: make every paid AI read transparent, intentional, and
economically useful for creators.

## Checkpoint 2 / repository progress summary

We are joining after Checkpoint 1, so this is our first progress update. Obol is
an existing project originally built for the Lepton Agents Hackathon, now
continued in a separate repository for the Arc Programmable Money Hackathon.
The working MVP already includes a Flask backend and web interface, a budgeted
research agent that records buy/reuse/skip decisions, Circle Wallets settlement
on Arc Testnet, a receipt ledger with Circle transaction IDs and Arc txHashes,
creator earnings views, a native agent API, and an x402-style HTTP 402 flow. We
froze the original Lepton submission and created this isolated iteration so
ongoing judging is unaffected. Next, we are adding clearer programmable
spending policies and accountability, refreshing live testnet evidence,
deploying a stable public demo, updating the README, and recording a new
three-minute demo. All testnet and evaluation activity will be labeled honestly.

## Track fit

Obol is not a chatbot wrapper or a scripted checkout. The agent receives a real
spending constraint and independently decides whether each source is worth
buying, should be reused from a prior purchase, or should be skipped. It may
stop spending when coverage is sufficient. When it buys, Circle Wallets settle
USDC on Arc Testnet and Obol records the reason and transaction proof. This
makes programmable money part of the agent's reasoning loop: relevance, price,
redundancy, coverage, and remaining budget directly determine whether money
moves. Creators gain machine-native pay-per-read revenue, while users gain an
auditable record of every cent spent.

## Existing-project disclosure

Obol was first built and submitted for the Lepton Agents Hackathon. We are
openly continuing that work for the Arc Programmable Money Hackathon in a
separate repository. The original submission remains frozen; this entry focuses
on new programmable budget controls, stronger agent accountability, refreshed
Circle/Arc proof, deployment, and a competition-specific demo. We are not
presenting Obol as a project started from scratch during this hackathon.

## Repository

https://github.com/xiangchengzilema/obol-programmable-money


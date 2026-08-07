/* Obol frontend - static, no build step. */

const DEV_STATIC_HOSTS = new Set(["localhost:5500", "127.0.0.1:5500"]);
const DEFAULT_API = DEV_STATIC_HOSTS.has(window.location.host)
  ? "http://localhost:5001"
  : window.location.origin;
const STORED_API = localStorage.getItem("obol_api");
const API_CANDIDATES = [...new Set([
  STORED_API,
  DEFAULT_API,
  window.location.origin,
  "http://localhost:5001",
  "http://127.0.0.1:5001",
].filter(Boolean).map((v) => v.replace(/\/$/, "")))];
let API = API_CANDIDATES[0];

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));
const fmt = (n, d = 4) => Number(n || 0).toFixed(d);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const shortHash = (h) => (h && h.length > 18 ? `${h.slice(0, 10)}...${h.slice(-6)}` : h || "");
const shortTime = (ts) => {
  if (!ts) return "--";
  const d = new Date(Number(ts) * 1000);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
};

let articles = [];
let creators = [];
let currentCreatorId = null;
let latestLedger = [];
let coverageAnim = null;
let dashboardPoll = null;
let paymentBubbleTimer = null;
let purchasePopoverAutoTimer = null;
let purchasePopoverHideTimer = null;
let primeDemoPromise = null;

function setActiveApi(base) {
  API = base.replace(/\/$/, "");
  localStorage.setItem("obol_api", API);
  const apiButton = $("#api-base");
  if (apiButton) apiButton.textContent = `API ${API}`;
}

function isNetworkFailure(err) {
  return err instanceof TypeError || /failed to fetch|network|load failed/i.test(String(err?.message || err));
}

async function api(path, opts = {}) {
  const tried = [];
  let lastNetworkError = null;
  const candidates = [API, ...API_CANDIDATES.filter((base) => base !== API)];
  for (const base of candidates) {
    tried.push(base);
    try {
      const r = await fetch(base + path, withLiveAuth(path, opts));
      if (!r.ok) {
        let msg = `${r.status} ${r.statusText}`;
        try { msg = (await r.json()).error || msg; } catch (_) {}
        throw new Error(`${msg} [${base}]`);
      }
      if (base !== API) setActiveApi(base);
      return r.json();
    } catch (err) {
      if (!isNetworkFailure(err)) throw err;
      lastNetworkError = err;
    }
  }
  throw new Error(`Network unavailable. Tried ${tried.join(", ")}. Last error: ${lastNetworkError?.message || "unknown"}`);
}

async function rawApi(path, opts = {}) {
  const tried = [];
  let lastNetworkError = null;
  const candidates = [API, ...API_CANDIDATES.filter((base) => base !== API)];
  for (const base of candidates) {
    tried.push(base);
    try {
      const r = await fetch(base + path, withLiveAuth(path, opts));
      let body = null;
      try { body = await r.json(); } catch (_) {}
      if (base !== API) setActiveApi(base);
      return { status: r.status, ok: r.ok, body };
    } catch (err) {
      if (!isNetworkFailure(err)) throw err;
      lastNetworkError = err;
    }
  }
  return { status: 0, ok: false, body: { error: `Network unavailable. Tried ${tried.join(", ")}. Last error: ${lastNetworkError?.message || "unknown"}` } };
}

function money(n, d = 4) {
  return `$${fmt(n, d)}`;
}

function withLiveAuth(path, opts = {}) {
  const next = { ...opts };
  const headers = new Headers(opts.headers || {});
  const token = sessionStorage.getItem("obol_live_api_token");
  const method = String(opts.method || "GET").toUpperCase();
  const needsLiveAuth = path.startsWith("/api/")
    && !["GET", "HEAD", "OPTIONS"].includes(method);
  if (token && needsLiveAuth && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  next.headers = headers;
  return next;
}

// Live deployments deliberately require an operator token. Keep it only in
// this tab's session storage; public mock deployments do not need one.
window.obolSetLiveApiToken = (token) => {
  if (token) sessionStorage.setItem("obol_live_api_token", String(token));
  else sessionStorage.removeItem("obol_live_api_token");
};

function withTimeout(promise, timeoutMs, message = "Request timed out") {
  let timer = null;
  return Promise.race([
    promise,
    new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(message)), timeoutMs);
    }),
  ]).finally(() => clearTimeout(timer));
}

function isLiveReceipt(receipt) {
  return receipt?.settlement_mode === "live"
    && receipt?.blockchain === "ARC-TESTNET"
    && Boolean(receipt?.tx_hash);
}

function receiptMode(receipt) {
  const mode = receipt?.settlement_mode;
  return ["live", "mock", "pending", "failed", "legacy"].includes(mode)
    ? mode
    : "legacy";
}

function isMockReceipt(receipt) {
  return receiptMode(receipt) === "mock";
}

function isPendingReceipt(receipt) {
  return receiptMode(receipt) === "pending";
}

function isFailedReceipt(receipt) {
  return receiptMode(receipt) === "failed";
}

function isSettledReceipt(receipt) {
  return isLiveReceipt(receipt) || isMockReceipt(receipt);
}

function receiptModeLabel(receipt) {
  if (isLiveReceipt(receipt)) return "live confirmed";
  if (isMockReceipt(receipt)) return "simulated / no funds moved";
  if (isPendingReceipt(receipt)) return "pending / content locked";
  if (isFailedReceipt(receipt)) return "failed / unpaid";
  return "unverified legacy receipt";
}

function ledgerSummary(ledger = []) {
  const live = ledger.filter(isLiveReceipt);
  const demo = ledger.filter(isMockReceipt);
  const unverified = ledger.filter((r) => !isSettledReceipt(r));
  const creators = new Set(live.map((r) => r.creator_name).filter(Boolean));
  const total = live.reduce((sum, r) => sum + Number(r.amount_usdc || 0), 0);
  const top = [...live].sort((a, b) => Number(b.amount_usdc || 0) - Number(a.amount_usdc || 0))[0] || null;
  return { live, demo, unverified, creators, total, top };
}

function renderHeroFeed(ledger = []) {
  const feed = $("#hero-live-feed");
  if (!feed) return;
  const rows = ledger.filter((r) => isSettledReceipt(r) && r.tx_hash).slice(0, 7);
  feed.innerHTML = rows.length ? rows.map((r) => `
    <p>
      <span>${esc(shortTime(r.created_at))}</span>
      <b>${esc(r.source || "agent")} / ${receiptModeLabel(r)}</b>
      <strong>${money(r.amount_usdc, 3)}</strong>
      <em>${esc(r.creator_name)}</em>
      <code>${esc(shortHash(r.tx_hash))}</code>
    </p>
  `).join("") : `<p>waiting for settlement receipts...</p>`;
}

function renderPaymentBubbles(ledger = []) {
  const shell = $("#payment-bubble-stream");
  if (!shell) return;
  const rows = ledger
    .filter((r) => isSettledReceipt(r) && r.tx_hash && r.creator_name)
    .slice(0, 6);

  if (!rows.length) {
    if (paymentBubbleTimer) clearInterval(paymentBubbleTimer);
    shell.classList.remove("is-single-feed", "is-bubble-cluster");
    shell.innerHTML = `
      <div class="payment-bubble-track is-static">
        <span class="payment-bubble is-loading">waiting for settlement receipts...</span>
      </div>
    `;
    return;
  }

  shell.classList.remove("is-single-feed");
  shell.classList.add("is-bubble-cluster");
  shell.innerHTML = `
    <div class="payment-bubble-track is-cluster">
      ${visiblePaymentBubbles(rows, 0)}
    </div>
  `;
  startPaymentBubbleTicker(shell, rows);
}

function visiblePaymentBubbles(rows, start = 0) {
  const visible = Math.min(2, rows.length);
  return Array.from({ length: visible }, (_, offset) => {
    const index = (start + offset) % rows.length;
    return paymentBubbleMarkup(rows[index], index);
  }).join("");
}

function paymentBubbleMarkup(r, index = 0) {
  const live = isLiveReceipt(r);
  return `
    <span class="payment-bubble ${index % 3 === 0 ? "is-hot" : index % 3 === 1 ? "is-cyan" : "is-amber"}">
      <span class="bubble-dot" aria-hidden="true"></span>
      <strong>${esc(r.creator_name)}</strong>
      <span>${live ? "received" : "demo receipt"}</span>
      <code>${money(r.amount_usdc, 3)} USDC</code>
    </span>
  `;
}

function startPaymentBubbleTicker(shell, rows = []) {
  if (paymentBubbleTimer) clearInterval(paymentBubbleTimer);
  const track = shell.querySelector(".payment-bubble-track");
  const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
  if (!track || rows.length < 2 || reduceMotion) {
    if (track) track.style.transform = "translate3d(0, 0, 0)";
    return;
  }

  let index = 0;
  const move = () => {
    if (!$("#view-home")?.classList.contains("active") || shell.matches(":hover")) return;
    index = (index + 1) % rows.length;
    track.classList.add("is-swapping");
    setTimeout(() => {
      track.innerHTML = track.classList.contains("is-cluster")
        ? visiblePaymentBubbles(rows, index)
        : paymentBubbleMarkup(rows[index], index);
      track.classList.remove("is-swapping");
    }, 170);
  };

  paymentBubbleTimer = setInterval(move, 2600);
}

async function updateDaemonDeck() {
  try {
    const d = await api("/api/usage-daemon");
    const paid = $("#daemon-paid");
    const state = $("#daemon-state");
    const deck = $("#deck-window");
    if (paid) paid.textContent = d.available ? `${d.paid_reads || 0} paid reads` : "runner idle";
    if (state) {
      state.textContent = d.running
        ? `${d.reused_reads || 0} reused / ${d.errors || 0} errors`
        : d.available
          ? `finished / ${d.reused_reads || 0} reused`
          : "no runner state yet";
    }
    if (deck) {
      deck.textContent = d.running
        ? "runner active now"
        : d.available
          ? `${d.paid_reads || 0} paid reads captured`
          : "runner ready";
    }
  } catch (_) {
    const state = $("#daemon-state");
    if (state) state.textContent = "runner state unavailable";
  }
}

async function refreshVisibleDashboard() {
  loadHealth();
  if ($("#view-home")?.classList.contains("active")) {
    await loadStats();
    await updateDaemonDeck();
  }
  if ($("#view-traction")?.classList.contains("active")) {
    await loadTraction();
  }
}

function showToast(message, kind = "ok") {
  const msg = $("#article-form-msg");
  if (msg) {
    msg.textContent = message;
    msg.className = `form-msg ${kind === "error" ? "error" : ""}`;
  }
}

function showView(name) {
  $$(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${name}`));
  $$(".navbtn").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  if (name !== "console") hidePurchasePopover();
  if (name !== "market") hideUnlockModal();
  if (name !== "traction") $("#receipt-drawer")?.classList.add("hidden");
  window.scrollTo({ top: 0, behavior: "auto" });
  if (name === "home") loadStats();
  if (name === "market") loadMarket();
  if (name === "creators") loadCreators();
  if (name === "x402") loadX402Articles();
  if (name === "traction") loadTraction();
}

function scrollToWithTopbar(selector, extra = 24) {
  const el = typeof selector === "string" ? $(selector) : selector;
  if (!el) return;
  const topbar = $(".topbar");
  const topbarHeight = topbar ? Math.ceil(topbar.getBoundingClientRect().height) : 88;
  const top = Math.max(0, el.getBoundingClientRect().top + window.scrollY - topbarHeight - extra);
  window.scrollTo({ top, behavior: "smooth" });
}

function animateCoverage(target, duration = 1400) {
  const label = $("#coverage-label");
  const bar = $("#coverage-bar");
  if (!label || !bar) return;
  if (coverageAnim) cancelAnimationFrame(coverageAnim);
  const current = Number(label.textContent.replace("%", "")) || 0;
  const end = Math.max(0, Math.min(100, Math.round(target)));
  const start = performance.now();
  const tick = (now) => {
    const t = Math.max(0, Math.min(1, (now - start) / duration));
    const eased = 1 - Math.pow(1 - t, 3);
    const value = Math.max(0, Math.min(100, Math.round(current + (end - current) * eased)));
    label.textContent = `${value}%`;
    bar.style.transform = `scaleX(${value / 100})`;
    if (t < 1) coverageAnim = requestAnimationFrame(tick);
  };
  coverageAnim = requestAnimationFrame(tick);
}

function setCoverageNow(value) {
  const label = $("#coverage-label");
  const bar = $("#coverage-bar");
  if (!label || !bar) return;
  if (coverageAnim) cancelAnimationFrame(coverageAnim);
  const safeValue = Math.max(0, Math.min(100, Math.round(value)));
  label.textContent = `${safeValue}%`;
  bar.style.transform = `scaleX(${safeValue / 100})`;
}

async function primeLiveDemo(runNow = false) {
  showView("console");
  $("#q-input").value = "Arc testnet predictable fees for high frequency payments";
  $("#b-input").value = "0.05";
  if (!runNow) return;
  if (primeDemoPromise) return primeDemoPromise;
  const launchers = ["#demo-path-btn", "#topbar-demo-btn", "#quick-demo-btn"]
    .map((selector) => $(selector))
    .filter(Boolean);
  launchers.forEach((button) => {
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
  });
  primeDemoPromise = (async () => {
    try {
      const ledger = latestLedger.length ? latestLedger : await api("/api/ledger");
      latestLedger = ledger;
      if (ledger.length) {
        await replayLatestLiveProof();
      } else {
        await runAgent();
      }
    } catch (_) {
      await runAgent();
    } finally {
      launchers.forEach((button) => {
        button.disabled = false;
        button.removeAttribute("aria-busy");
      });
      primeDemoPromise = null;
    }
  })();
  return primeDemoPromise;
}

async function replayLatestLiveProof() {
  const btn = $("#quick-demo-btn");
  const runBtn = $("#run-btn");
  const query = $("#q-input").value.trim() || "Arc testnet predictable fees for high frequency payments";
  const dashboard = $("#run-dashboard");
  const resultStage = $("#run-result");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Replaying receipt...";
  }
  if (runBtn) {
    runBtn.disabled = true;
    runBtn.textContent = "Receipt replay...";
  }
  $("#empty-run")?.classList.add("hidden");
  dashboard?.classList.remove("hidden");
  dashboard?.classList.add("is-running");
  resultStage?.classList.add("agent-running");
  $("#decision-section")?.classList.remove("hidden");
  hidePurchasePopover();
  renderRunSteps("running");
  renderChainLens();
  renderMarketScan("searching", null, query);
  $("#r-plan").innerHTML = `<span class="loading">reading the latest settlement receipt and replaying the agent decision path...</span>`;
  $("#r-summary").innerHTML = "";
  $("#r-proof-grid").innerHTML = "";
  $("#r-decisions").innerHTML = "";
  $("#r-receipts").innerHTML = "";
  $("#r-answer").textContent = "";
  $("#r-confidence").textContent = "";
  $("#coverage-title").textContent = "Settlement Receipt Replay";
  $("#coverage-note").textContent = "Scanning existing receipts and preserving their live or simulated status.";
  setCoverageNow(0);

  const timers = [
    setTimeout(() => {
      renderRunSteps("choosing");
      animateCoverage(34, 520);
    }, 220),
    setTimeout(() => {
      renderRunSteps("settling");
      animateCoverage(72, 620);
      showPendingPurchasePopover(query, Number($("#b-input").value || 0.011));
      $("#purchase-kicker").textContent = "Settlement receipt located";
      $("#purchase-proof").textContent = "matching a receipt from the auditable ledger";
    }, 720),
    setTimeout(() => {
      renderRunSteps("proving");
      animateCoverage(94, 580);
      $("#purchase-kicker").textContent = "Receipt proof loading";
      $("#purchase-proof").textContent = "proof id found / checking settlement mode";
    }, 1240),
  ];

  try {
    const ledger = latestLedger.length ? latestLedger : await api("/api/ledger");
    latestLedger = ledger;
    const receipt = ledger.find(isLiveReceipt) || ledger.find(isMockReceipt);
    if (!receipt) throw new Error("No receipt available yet. Run the agent first.");
    const liveSettlement = isLiveReceipt(receipt);
    const amount = Number(receipt.amount_usdc || 0.011);
    const budget = Math.max(0.011, amount + 0.002);
    const run = {
      id: "replay",
      query,
      budget_usdc: budget,
      total_spent: amount,
      budget_remaining: Math.max(0, budget - amount),
      coverage: 0.93,
      saved_usdc: 0,
      sources_used: 1,
      confidence: "high",
      settlement_mode: liveSettlement ? "live" : "mock",
      plan: liveSettlement
        ? "Replay a live paid read: score paid sources, select the strongest match, then surface its Circle transaction and Arc Testnet txHash."
        : "Replay a simulated public-demo read: score paid sources, select the strongest match, then surface its non-chain demo receipt.",
      answer: liveSettlement
        ? `The agent selected "${receipt.title}" because the source matched the query and had a verified live payment receipt. The creator received ${money(amount)} through Circle Wallets, with the Arc txHash attached as proof.`
        : `The agent selected "${receipt.title}" because the source matched the query. This public-demo run simulated a ${money(amount)} settlement; its receipt is explicitly marked mock and is not an on-chain payment.`,
      decisions: [
        {
          decision: "buy",
          title: receipt.title,
          creator_name: receipt.creator_name,
          relevance: 1,
          price_usdc: amount,
          reason: liveSettlement
            ? "latest live Arc receipt selected for a deterministic judge demo"
            : "latest simulated receipt selected for a deterministic public demo",
        },
        {
          decision: "skip",
          title: "Lower relevance source",
          creator_name: "market scan",
          relevance: 0.28,
          price_usdc: amount,
          reason: "below the relevance bar; no payment needed",
        },
        {
          decision: "skip",
          title: "Redundant cached source",
          creator_name: "market scan",
          relevance: 0.18,
          price_usdc: amount,
          reason: "same topic already covered; budget preserved",
        },
      ],
      receipts: [{
        title: receipt.title,
        creator_name: receipt.creator_name,
        amount_usdc: amount,
        tx_hash: receipt.tx_hash,
        transaction_id: receipt.transaction_id,
        blockchain: receipt.blockchain || (liveSettlement ? "ARC-TESTNET" : "SIMULATED-ARC-TESTNET"),
        settlement_mode: liveSettlement ? "live" : "mock",
      }],
    };
    await new Promise((resolve) => setTimeout(resolve, 1850));
    timers.forEach((timer) => clearTimeout(timer));
    renderRun(run);
    renderRunSteps("done");
    renderMarketScan("done", run, query);
    showPurchasePopover(run);
    renderHeroFeed(ledger);
    await loadStats();
  } catch (e) {
    timers.forEach((timer) => clearTimeout(timer));
    $("#r-plan").innerHTML = `<span class="error">${esc(e.message)}</span>`;
  } finally {
    dashboard?.classList.remove("is-running");
    resultStage?.classList.remove("agent-running");
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Replay latest receipt";
    }
    if (runBtn) {
      runBtn.disabled = false;
      runBtn.textContent = "Run agent";
    }
  }
}

async function loadHealth() {
  const pill = $("#mode-pill");
  try {
    const h = await api("/api/health");
    const liveReady = h.settlement_mode === "live" && h.settlement_ready;
    pill.textContent = liveReady ? `Arc live ready / llm ${h.llm_mode}` : `mock settlement / llm ${h.llm_mode}`;
    pill.className = `pill ${liveReady ? "pill-ok" : "pill-warn"}`;
  } catch (e) {
    pill.textContent = "backend offline";
    pill.className = "pill pill-muted";
  }
}

const STAT_CARDS = [
  ["live_paid_usdc", "live paid", (v) => money(v)],
  ["live_reads", "live reads", (v) => v],
  ["demo_reads", "simulated reads", (v) => v],
  ["num_runs", "runs", (v) => v],
  ["decisions_made", "decisions", (v) => v],
  ["usdc_saved_by_reuse", "saved", (v) => money(v)],
  ["num_creators", "creators", (v) => v],
];

async function loadStats() {
  const grid = $("#stats-grid");
  grid.innerHTML = `<p class="loading">loading dashboard...</p>`;
  try {
    const s = await api("/api/stats");
    grid.innerHTML = STAT_CARDS.map(([k, label, format]) => `
      <article class="stat">
        <div class="num">${format(s[k])}</div>
        <div class="lbl">${label}</div>
      </article>
    `).join("");
    const heroAmount = $("#hero-proof-amount");
    const receiptVolume = Number(s.live_paid_usdc || 0) || Number(s.demo_paid_usdc || 0);
    if (heroAmount && receiptVolume) heroAmount.textContent = money(receiptVolume);
    loadLiveProof(s);
  } catch (e) {
    grid.innerHTML = `<p class="error">Cannot reach backend at ${esc(API)}: ${esc(e.message)}</p>`;
  }
}

async function loadLiveProof(stats = null) {
  const box = $("#live-proof");
  if (!box) return;
  try {
    const ledger = await api("/api/ledger");
    latestLedger = ledger;
    renderHeroFeed(ledger);
    renderPaymentBubbles(ledger);
    const { live, demo, creators, total, top } = ledgerSummary(ledger);
    const liveMode = live.length > 0;
    const active = liveMode ? live : demo;
    const proof = active[0];
    const activeCreators = liveMode
      ? creators
      : new Set(demo.map((r) => r.creator_name).filter(Boolean));
    const demoTotal = demo.reduce(
      (sum, receipt) => sum + Number(receipt.amount_usdc || 0),
      0,
    );
    const paidTotal = Number(
      liveMode
        ? (stats?.live_paid_usdc ?? total)
        : (stats?.demo_paid_usdc ?? demoTotal),
    );
    if (!proof) {
      box.innerHTML = `
        <div>
          <span class="section-label">Settlement proof</span>
          <h3>Waiting for a completed receipt</h3>
          <p>Run the agent to produce a clearly labelled live or simulated receipt.</p>
        </div>
        <span class="pill pill-muted">no receipt yet</span>
      `;
      const heroStatus = $("#hero-proof-status");
      if (heroStatus) {
        heroStatus.textContent = "no receipt yet";
        heroStatus.className = "pill pill-muted";
      }
      const demoAmount = $("#demo-director-amount");
      const demoHash = $("#demo-director-hash");
      if (demoAmount) demoAmount.textContent = "$0.0000 USDC";
      if (demoHash) demoHash.textContent = "waiting";
      return;
    }
    box.innerHTML = `
      <div>
        <span class="section-label">${liveMode ? "Live Arc proof" : "Demo receipt"}</span>
        <h3>${money(paidTotal)} ${liveMode ? "settled" : "simulated"} across ${activeCreators.size} creators</h3>
        <p>${liveMode
          ? `Latest: ${money(proof.amount_usdc)} to ${esc(proof.creator_name)} / Circle ${esc(shortHash(proof.transaction_id))}`
          : `Latest: ${money(proof.amount_usdc)} simulated for ${esc(proof.creator_name)} / not on-chain`}</p>
        <code>${esc(proof.tx_hash)}</code>
      </div>
      <span class="pill ${liveMode ? "pill-ok" : "pill-warn"}">${liveMode ? "Arc Testnet complete" : "simulated / not on-chain"}</span>
    `;
    const heroStatus = $("#hero-proof-status");
    const heroAmount = $("#hero-proof-amount");
    const heroTitle = $("#hero-proof-title");
    const heroLink = $("#hero-proof-link");
    const heroHash = $("#hero-proof-hash");
    if (heroStatus) {
      heroStatus.textContent = liveMode ? "confirmed" : "simulated";
      heroStatus.className = `pill ${liveMode ? "pill-ok" : "pill-warn"}`;
    }
    if (heroAmount) heroAmount.textContent = money(paidTotal);
    if (heroTitle) {
      heroTitle.textContent = `${activeCreators.size} creators / ${active.length} ${liveMode ? "live" : "demo"} receipts`;
      heroTitle.title = liveMode && top
        ? `Largest live receipt: ${money(top.amount_usdc)} to ${top.creator_name}`
        : "Public-demo receipts are simulated and not on-chain.";
    }
    if (heroHash) heroHash.textContent = shortHash(proof.tx_hash);
    if (heroLink) heroLink.href = `#tx-${encodeURIComponent(proof.tx_hash)}`;
    const demoAmount = $("#demo-director-amount");
    const demoHash = $("#demo-director-hash");
    if (demoAmount) demoAmount.textContent = `${money(paidTotal)} USDC`;
    if (demoHash) demoHash.textContent = shortHash(proof.tx_hash);
    const deckMarket = $("#deck-market");
    const deckCreators = $("#deck-creators");
    if (deckMarket) deckMarket.textContent = `${Math.max(articles.length || 0, 100)} paid sources`;
    if (deckCreators) {
      deckCreators.textContent = liveMode
        ? `${activeCreators.size} creator wallets paid`
        : `${activeCreators.size} creator payouts simulated`;
    }
  } catch (_) {}
}

async function verifyEvaluationEvidence(evidence) {
  const status = $("#evidence-live-status");
  const detail = $("#evidence-live-detail");
  const button = $("#verify-evidence-btn");
  if (!status || !detail || !button) return;
  status.textContent = "checking Arc RPC";
  status.className = "pill pill-muted";
  button.disabled = true;
  button.textContent = "Verifying...";
  try {
    const hash = evidence.arc.transaction_hash;
    const proof = await withTimeout(
      api(`/api/arc/transactions/${encodeURIComponent(hash)}/verify`),
      12000,
      "Arc RPC verification timed out",
    );
    if (proof.verified !== true || proof.successful !== true || proof.evidence_match !== true) {
      throw new Error("on-chain receipt did not match the committed agent evidence");
    }
    const transfer = proof.matched_transfer;
    if (!transfer) throw new Error("bound USDC Transfer event was not returned");
    status.textContent = "live RPC confirmed";
    status.className = "pill pill-ok";
    const block = Number(
      proof.receipt?.block_number || proof.block?.number || evidence.arc.block_number
    ).toLocaleString();
    detail.textContent = `Strict match via ${proof.rpc_host || "Arc Testnet RPC"} / payer, token, recipient, ${transfer.amount_usdc} USDC, and block ${block}`;
  } catch (error) {
    status.textContent = "saved proof available";
    status.className = "pill pill-warn";
    detail.textContent = `Live re-check unavailable: ${error.message}. The committed two-endpoint snapshot and Arcscan link remain available.`;
  } finally {
    button.disabled = false;
    button.textContent = "Verify again";
  }
}

async function loadEvaluationEvidence(retryCount = 0) {
  const box = $("#verified-evidence");
  if (!box) return;
  try {
    const evidence = await withTimeout(
      api("/api/evidence/latest"),
      10000,
      "Evidence endpoint timed out",
    );
    const run = evidence.agent_run;
    const arc = evidence.arc;
    const circle = evidence.circle;
    const generated = new Date(evidence.generated_at).toLocaleString([], {
      year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
    box.innerHTML = `
      <header class="verified-evidence-head">
        <div>
          <span class="section-label">Fresh evidence / ${esc(generated)}</span>
          <h2 id="verified-evidence-title">One agent decision. One real testnet receipt.</h2>
          <p>${esc(evidence.disclosure)}</p>
        </div>
        <span id="evidence-live-status" class="pill pill-muted">checking Arc RPC</span>
      </header>
      <div class="verified-evidence-grid">
        <div class="evidence-story">
          <div class="evidence-amount-row">
            <strong>${money(arc.amount_usdc, 2)}</strong>
            <span>USDC paid to ${esc(run.creator)}</span>
          </div>
          <div class="evidence-metrics" aria-label="Agent budget evidence">
            <article><span>Budget</span><strong>${money(run.budget_usdc, 2)}</strong></article>
            <article><span>Spent</span><strong>${money(run.total_spent_usdc, 2)}</strong></article>
            <article><span>Preserved</span><strong>${money(run.budget_remaining_usdc, 2)}</strong></article>
            <article><span>Coverage</span><strong>${Math.round(Number(run.coverage_achieved) * 100)}%</strong></article>
          </div>
          <div class="evidence-decision-trace">
            <div><b>BUY</b><span>${esc(run.article)}</span><small>best match within the per-source cap</small></div>
            <div><b>SKIP</b><span>${Number(run.decision_counts.skip)} candidates</span><small>weak, redundant, or outside policy</small></div>
            <div><b>STOP</b><span>${esc(run.stop_rule.replaceAll("_", " "))}</span><small>${esc(run.stop_reason)}</small></div>
          </div>
        </div>
        <aside class="evidence-receipt" aria-label="Verified Arc Testnet receipt">
          <div class="evidence-route" aria-label="Settlement route">
            <span>Agent</span><i></i><span>Circle Wallets</span><i></i><span>Arc Testnet</span>
          </div>
          <dl>
            <div><dt>Circle state</dt><dd>${esc(circle.state)}</dd></div>
            <div><dt>Arc block</dt><dd>#${Number(arc.block_number).toLocaleString()}</dd></div>
            <div><dt>Asset</dt><dd>USDC / Arc Testnet</dd></div>
            <div><dt>Recipient</dt><dd><code>${esc(shortHash(arc.creator_address))}</code></dd></div>
          </dl>
          <div class="evidence-hash">
            <span>Transaction hash</span>
            <code>${esc(arc.transaction_hash)}</code>
          </div>
          <p id="evidence-live-detail">Saved receipt was independently checked through two Arc RPC endpoints; the button re-checks through the primary with fallback.</p>
          <div class="evidence-actions">
            <a class="primary" href="${esc(arc.explorer_url)}" target="_blank" rel="noreferrer">Open in Arcscan</a>
            <button class="secondary" id="verify-evidence-btn" type="button">Verify again</button>
          </div>
        </aside>
      </div>
    `;
    $("#verify-evidence-btn")?.addEventListener("click", () => verifyEvaluationEvidence(evidence));
    verifyEvaluationEvidence(evidence);
  } catch (error) {
    box.innerHTML = `
      <div class="verified-evidence-loading">
        <span class="section-label">Fresh Arc evidence</span>
        <h2 id="verified-evidence-title">Evidence endpoint is warming up.</h2>
        <p>${esc(error.message)}</p>
        <button class="secondary" id="retry-evidence-btn" type="button">Retry evidence</button>
      </div>
    `;
    $("#retry-evidence-btn")?.addEventListener("click", () => loadEvaluationEvidence(1));
    if (retryCount < 1) {
      setTimeout(() => loadEvaluationEvidence(retryCount + 1), 1800);
    }
  }
}

async function resetDemoData() {
  const btn = $("#reset-demo-btn");
  btn.disabled = true;
  btn.textContent = "Resetting...";
  try {
    await api("/api/demo/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    clearRun();
    await Promise.all([loadStats(), loadMarket(), loadCreators(), loadX402Articles()]);
    btn.textContent = "Demo data reset";
    setTimeout(() => { btn.textContent = "Reset demo data"; }, 1300);
  } catch (e) {
    if (String(e.message).includes("live receipts")) {
      const ok = confirm("This database contains live Arc receipts. Resetting removes local demo evidence, although the on-chain tx remains. Continue?");
      if (ok) {
        await api("/api/demo/reset", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ confirm_live_reset: true }),
        });
        clearRun();
        await Promise.all([loadStats(), loadMarket(), loadCreators(), loadX402Articles()]);
        btn.textContent = "Demo data reset";
        setTimeout(() => { btn.textContent = "Reset demo data"; }, 1300);
        return;
      }
    }
    btn.textContent = "Reset failed";
    showToast(`Reset failed: ${e.message}`, "error");
    setTimeout(() => { btn.textContent = "Reset demo data"; }, 1800);
  } finally {
    btn.disabled = false;
  }
}

function clearRun() {
  $("#empty-run").classList.remove("hidden");
  $("#run-dashboard").classList.add("hidden");
  $("#run-dashboard").classList.remove("is-running");
  $("#run-result").classList.remove("agent-running");
  hidePurchasePopover();
  $("#decision-section").classList.add("hidden");
  $("#r-decisions").innerHTML = "";
  $("#r-receipts").innerHTML = "";
  $("#r-answer").textContent = "";
  $("#r-proof-grid").innerHTML = "";
  renderMarketScan("idle");
  renderRunSteps("idle");
  renderChainLens();
}

function renderMarketScan(state = "idle", run = null, query = "") {
  const lane = $("#scan-lane");
  const headline = $("#scan-headline");
  const status = $("#scan-status");
  if (!lane || !headline || !status) return;

  const setHead = (text, mode) => {
    headline.textContent = text;
    status.textContent = mode;
  };

  if (state === "idle") {
    setHead("Waiting for agent run", "idle");
    lane.innerHTML = [
      ["01", "Search creator market", "Find locked sources that match the query.", ""],
      ["02", "Score relevance", "Rank content by usefulness and price.", ""],
      ["03", "Authorize payment", "Buy only when the source clears the bar.", ""],
      ["04", "Return proof", "Show Circle transaction and Arc txHash.", ""],
    ].map(([step, title, body, code]) => scanCard(step, title, body, code)).join("");
    return;
  }

  if (state === "searching") {
    setHead(`Searching paid sources for "${query.slice(0, 72)}${query.length > 72 ? "..." : ""}"`, "searching");
    lane.innerHTML = [
      ["01", "Query received", `${money($("#b-input").value)} budget available for one answer.`, "budget locked"],
      ["02", "Scanning marketplace", "Checking paid previews, tags, and creator history.", "content graph"],
      ["03", "Scoring candidates", "Relevance, price, cache reuse, and coverage are being compared.", "agent policy"],
      ["04", "Waiting for settlement", "No USDC moves until a source is selected.", "not paid yet"],
    ].map(([step, title, body, code], index) => scanCard(step, title, body, code, index <= 2 ? "is-active" : "")).join("");
    return;
  }

  const decisions = (run?.decisions || []).slice(0, 4);
  const receipt = (run?.receipts || [])[0];
  const cards = decisions.length ? decisions.map((d, index) => {
    const cls = d.decision === "buy" ? "is-buy" : d.decision === "reuse" ? "is-reuse" : "is-skip";
    const detail = d.decision === "buy"
      ? `${money(d.price_usdc, 3)} paid to ${d.creator_name}`
      : d.decision === "reuse"
        ? `${money(d.price_usdc, 3)} saved by prior receipt`
        : `Skipped: ${d.reason}`;
    return scanCard(`0${index + 1}`, d.title, detail, `relevance ${fmt(d.relevance, 2)}`, cls);
  }) : [
    scanCard("01", "No source purchased", "The agent did not find a paid read worth buying.", "no transfer", "is-skip"),
  ];

  if (receipt) {
    const live = isLiveReceipt(receipt);
    const mock = isMockReceipt(receipt);
    const pending = isPendingReceipt(receipt);
    setHead(
      `${live ? "Purchased" : mock ? "Simulated purchase" : pending ? "Settlement pending" : "Settlement failed"} "${receipt.title}"`,
      live ? "paid" : mock ? "demo" : pending ? "pending" : "failed",
    );
    const txCard = scanCard(
      "TX",
      live ? "Arc receipt confirmed" : mock ? "Demo receipt recorded" : pending ? "Circle confirmation pending" : "Settlement not completed",
      live
        ? `${money(receipt.amount_usdc)} moved through Circle Wallets.`
        : mock
          ? `${money(receipt.amount_usdc)} simulated; no on-chain funds moved.`
          : pending
            ? `${money(receipt.amount_usdc)} reserved; content remains locked.`
            : `${money(receipt.amount_usdc)} was not counted as paid.`,
      shortHash(receipt.tx_hash || receipt.transaction_id),
      "is-buy",
    );
    lane.innerHTML = [...cards.slice(0, 3), txCard].join("");
    return;
  } else if (run?.saved_usdc > 0) {
    setHead("Reused a prior paid read", "reused");
    const cacheCard = scanCard("CACHE", "Prior receipt reused", `${money(run.saved_usdc)} preserved by cache reuse.`, "no new transfer", "is-reuse");
    lane.innerHTML = [...cards.slice(0, 3), cacheCard].join("");
    return;
  } else {
    setHead("No purchase made", "skipped");
  }
  lane.innerHTML = cards.slice(0, 4).join("");
}

function scanCard(step, title, body, code = "", cls = "") {
  return `
    <article class="scan-card ${cls}">
      <span>${esc(step)}</span>
      <strong>${esc(title)}</strong>
      <p>${esc(body)}</p>
      ${code ? `<code>${esc(code)}</code>` : ""}
    </article>
  `;
}

function clearPurchasePopoverTimers() {
  if (purchasePopoverAutoTimer) clearTimeout(purchasePopoverAutoTimer);
  if (purchasePopoverHideTimer) clearTimeout(purchasePopoverHideTimer);
  purchasePopoverAutoTimer = null;
  purchasePopoverHideTimer = null;
}

function hidePurchasePopover({ immediate = false } = {}) {
  const pop = $("#purchase-popover");
  clearPurchasePopoverTimers();
  if (pop?.classList.contains("hidden")) {
    $("#run-dashboard")?.classList.remove("purchase-open");
    return;
  }
  if (pop) {
    pop.classList.remove("is-visible", "is-updating");
    if (immediate) {
      pop.classList.remove("is-leaving");
      pop.classList.add("hidden");
    } else {
      pop.classList.add("is-leaving");
      purchasePopoverHideTimer = setTimeout(() => {
        pop.classList.add("hidden");
        pop.classList.remove("is-leaving");
      }, 220);
    }
  }
  $("#run-dashboard")?.classList.remove("purchase-open");
}

function showPendingPurchasePopover(query, budget, phase = "scan") {
  const pop = $("#purchase-popover");
  if (!pop) return;
  clearPurchasePopoverTimers();
  const copy = {
    scan: [
      "Scoring sources",
      "Budget locked for one answer",
      `${money(budget)} is available. The agent is ranking paid articles by relevance, price, and prior receipts before any USDC moves.`,
      `intent: ${query.slice(0, 72)}${query.length > 72 ? "..." : ""}`,
    ],
    decide: [
      "Source policy",
      "Buy, reuse, or skip",
      "The agent is deciding whether a paid source is useful enough, or whether an existing receipt already covers the answer.",
      "policy: relevance / price / cache boundary",
    ],
    proof: [
      "Binding receipt",
      "Preparing verifiable proof",
      "A new buy returns a Circle transfer and Arc txHash. A cache hit returns the previous valid receipt.",
      "finalizing: buy / cache hit / skip",
    ],
  }[phase] || [];
  $("#purchase-kicker").textContent = copy[0] || "Agent running";
  $("#purchase-title").textContent = copy[1] || "Scanning paid sources";
  $("#purchase-meta").textContent = copy[2] || `${money(budget)} budget locked.`;
  $("#purchase-proof-label").textContent = "Agent state";
  $("#purchase-proof").textContent = copy[3] || "waiting for agent decision";
  pop.dataset.phase = phase;
  $("#run-dashboard")?.classList.add("purchase-open");
  pop.classList.remove("hidden", "is-leaving");
  requestAnimationFrame(() => pop.classList.add("is-visible"));
}

function updatePurchasePopover(kicker, title, meta, proof, label = "Arc proof") {
  const pop = $("#purchase-popover");
  if (!pop) return;
  clearPurchasePopoverTimers();
  $("#purchase-kicker").textContent = kicker;
  $("#purchase-title").textContent = title;
  $("#purchase-meta").textContent = meta;
  $("#purchase-proof-label").textContent = label;
  $("#purchase-proof").textContent = proof;
  pop.dataset.phase = /fail|error|unavailable/i.test(kicker + title)
    ? "error"
    : /complete|receipt|proof|purchase/i.test(kicker + title + label)
      ? "proof"
      : "decide";
  $("#run-dashboard")?.classList.add("purchase-open");
  pop.classList.remove("hidden", "is-leaving");
  pop.classList.add("is-visible", "is-updating");
  setTimeout(() => pop.classList.remove("is-updating"), 220);
}

function schedulePurchasePopoverHide(delay = 3400) {
  if (purchasePopoverAutoTimer) clearTimeout(purchasePopoverAutoTimer);
  purchasePopoverAutoTimer = setTimeout(() => hidePurchasePopover(), delay);
}

function setUnlockProgress(value) {
  const bar = $("#unlock-progress-bar");
  if (bar) bar.style.transform = `scaleX(${Math.max(0, Math.min(100, value)) / 100})`;
}

function setUnlockStep(step) {
  const order = ["submit", "settle", "proof"];
  order.forEach((name, index) => {
    const el = $(`#unlock-step-${name}`);
    if (!el) return;
    const current = order.indexOf(step);
    el.className = index < current ? "done" : index === current ? "active" : "";
  });
}

function showUnlockModal(article) {
  const modal = $("#unlock-modal");
  if (!modal) return;
  modal.classList.remove("hidden", "is-error");
  $("#unlock-kicker").textContent = "Unlocking source";
  $("#unlock-title").textContent = article.title;
  $("#unlock-meta").textContent = `${money(article.price_usdc, 3)} USDC will be paid to ${article.creator_name}.`;
  $("#unlock-proof-label").textContent = "Status";
  $("#unlock-proof").textContent = "Submitting Circle wallet transfer";
  setUnlockStep("submit");
  setUnlockProgress(12);
  setTimeout(() => setUnlockProgress(38), 160);
}

function updateUnlockModal(state, payload = {}) {
  const modal = $("#unlock-modal");
  if (!modal) return;
  if (state === "settling") {
    $("#unlock-kicker").textContent = "Circle transfer submitted";
    $("#unlock-meta").textContent = "Waiting for Arc Testnet confirmation. This can take a few seconds.";
    $("#unlock-proof").textContent = "Polling Circle for txHash";
    setUnlockStep("settle");
    setUnlockProgress(68);
  }
  if (state === "success") {
    const live = isLiveReceipt(payload.receipt);
    modal.classList.remove("is-error");
    $("#unlock-kicker").textContent = live ? "Purchase complete" : "Demo purchase complete";
    $("#unlock-title").textContent = payload.title || "Source unlocked";
    $("#unlock-meta").textContent = live
      ? `${payload.creator_name || "Creator"} received ${money(payload.amount_paid_usdc)}.`
      : `${money(payload.amount_paid_usdc)} was simulated for ${payload.creator_name || "Creator"}; no on-chain funds moved.`;
    $("#unlock-proof-label").textContent = live ? "Arc proof" : "Demo receipt";
    $("#unlock-proof").textContent = payload.receipt?.tx_hash || payload.receipt?.transaction_id || "receipt recorded";
    setUnlockStep("proof");
    $("#unlock-step-submit").className = "done";
    $("#unlock-step-settle").className = "done";
    $("#unlock-step-proof").className = "done";
    setUnlockProgress(100);
  }
  if (state === "pending") {
    modal.classList.remove("is-error");
    $("#unlock-kicker").textContent = "Settlement pending";
    $("#unlock-title").textContent = payload.title || "Source remains locked";
    $("#unlock-meta").textContent = "Circle has not reported COMPLETE. The amount is reserved, no retry will be sent, and paid content stays locked.";
    $("#unlock-proof-label").textContent = "Pending Circle transaction";
    $("#unlock-proof").textContent = payload.receipt?.transaction_id || payload.receipt?.tx_hash || "durable payment claim recorded";
    setUnlockStep("settle");
    setUnlockProgress(72);
  }
  if (state === "error") {
    modal.classList.add("is-error");
    $("#unlock-kicker").textContent = "Unlock failed";
    $("#unlock-meta").textContent = "The wallet transfer did not complete. You can retry.";
    $("#unlock-proof-label").textContent = "Error";
    $("#unlock-proof").textContent = payload.message || "unknown error";
    setUnlockProgress(100);
  }
}

function hideUnlockModal() {
  $("#unlock-modal")?.classList.add("hidden");
}

function showPurchasePopover(run) {
  const pop = $("#purchase-popover");
  if (!pop) return;
  const receipt = (run.receipts || [])[0];
  const reused = (run.decisions || []).find((d) => d.decision === "reuse");
  const bought = (run.decisions || []).find((d) => d.decision === "buy");
  const selected = receipt || bought || reused;
  if (receipt) {
    if (isPendingReceipt(receipt)) {
      updatePurchasePopover(
        "Settlement pending",
        receipt.title || "Source remains locked",
        "The transfer amount is reserved, but Circle has not reported COMPLETE. Obol will not retry or release paid content yet.",
        receipt.transaction_id || receipt.tx_hash || "durable pending claim",
        "Pending proof",
      );
      return;
    }
    if (isFailedReceipt(receipt)) {
      updatePurchasePopover(
        "Settlement failed",
        receipt.title || "Source not purchased",
        "Circle reported a terminal failure. No content was released and the failed amount is not counted as paid.",
        receipt.transaction_id || "terminal failure recorded",
        "Failure proof",
      );
      schedulePurchasePopoverHide(4600);
      return;
    }
    const live = isLiveReceipt(receipt);
    updatePurchasePopover(
      live ? "Purchase complete" : "Demo purchase complete",
      receipt.title || "Source purchased",
      live
        ? `${receipt.creator_name} received ${money(receipt.amount_usdc)} on Arc Testnet`
        : `${money(receipt.amount_usdc)} was simulated for ${receipt.creator_name}; no on-chain funds moved`,
      receipt.tx_hash || receipt.transaction_id || "receipt recorded",
      live ? "Arc txHash" : "Demo receipt",
    );
    schedulePurchasePopoverHide(3800);
    return;
  }
  if (reused) {
    updatePurchasePopover(
      "Cache receipt reused",
      reused.title || "Prior paid source reused",
      `${reused.creator_name || "Creator"} was already paid for this source. The agent used that receipt instead of charging again.`,
      `${money(run.saved_usdc || reused.price_usdc)} preserved / no new transfer`,
      "Reuse proof",
    );
    schedulePurchasePopoverHide(3800);
    return;
  }
  if (bought || selected) {
    updatePurchasePopover(
      "Source selected",
      selected.title || "Paid source selected",
      `${selected.creator_name || "Creator"} selected by relevance. Settlement proof is being recorded.`,
      "source selected by agent policy",
      "Agent decision",
    );
    schedulePurchasePopoverHide(3200);
    return;
  }
  updatePurchasePopover(
    "No purchase needed",
    "The agent skipped paid sources",
    "No source cleared the relevance and budget policy, so no USDC moved.",
    "0.0000 USDC transferred",
    "Decision proof",
  );
  schedulePurchasePopoverHide(3200);
}

function renderRunSteps(state = "idle") {
  const box = $("#run-steps");
  if (!box) return;
  const labels = ["Read intent", "Choose source", "Move USDC", "Show receipt"];
  const stateIndex = {
    idle: 0,
    running: 1,
    choosing: 2,
    settling: 3,
    proving: 3,
    done: 4,
  };
  const activeIndex = stateIndex[state] ?? 0;
  box.innerHTML = labels.map((label, index) => {
    const cls = index < activeIndex ? "done" : index === activeIndex ? "active" : "";
    return `<span class="${cls}">${esc(label)}</span>`;
  }).join("");
}

function renderChainLens(run = null) {
  const set = (id, text) => {
    const el = $(id);
    if (el) el.textContent = text;
  };
  if (!run) {
    set("#lens-intent", "Agent has a budgeted query");
    set("#lens-decision", "Waiting for source choice");
    set("#lens-execution", "Waiting for settlement");
    set("#lens-receipt", "Waiting for txHash");
    return;
  }
  const decisions = run.decisions || [];
  const receipt = (run.receipts || [])[0];
  const bought = decisions.find((d) => d.decision === "buy");
  const reused = decisions.find((d) => d.decision === "reuse");
  const skipped = decisions.filter((d) => d.decision === "skip").length;
  const chosen = bought || reused || decisions[0];

  set("#lens-intent", `${money(run.budget_usdc)} budget for one answer`);
  if (chosen) {
    set("#lens-decision", `${chosen.decision.toUpperCase()} - ${chosen.title}`);
  } else {
    set("#lens-decision", "No source met the bar");
  }
  if (receipt) {
    const mode = receiptMode(receipt);
    set(
      "#lens-execution",
      mode === "live"
        ? `${money(receipt.amount_usdc)} moved by Circle`
        : mode === "mock"
          ? `${money(receipt.amount_usdc)} simulated in demo mode`
          : mode === "pending"
            ? `${money(receipt.amount_usdc)} reserved / content locked`
            : mode === "failed"
              ? "Circle transfer failed / unpaid"
              : "Receipt unverified / excluded",
    );
    set("#lens-receipt", shortHash(receipt.tx_hash || receipt.transaction_id));
  } else if (reused) {
    set("#lens-execution", `${money(run.saved_usdc)} saved by cache reuse`);
    set("#lens-receipt", "Prior receipt reused");
  } else {
    set("#lens-execution", "No USDC moved");
    set("#lens-receipt", `${skipped} sources skipped`);
  }
}

async function runAgent() {
  const query = $("#q-input").value.trim();
  const budget = Number($("#b-input").value);
  if (!query || !budget || budget <= 0) return;
  const policy = {
    reserve_usdc: Number($("#policy-reserve").value),
    max_price_usdc: Number($("#policy-max-price").value),
    min_relevance: Number($("#policy-min-relevance").value),
    max_purchases: Number($("#policy-max-purchases").value),
  };

  const btn = $("#run-btn");
  const resultStage = $("#run-result");
  const dashboard = $("#run-dashboard");
  btn.disabled = true;
  btn.textContent = "Agent deciding...";
  $("#empty-run").classList.add("hidden");
  dashboard.classList.remove("hidden");
  dashboard.classList.add("is-running");
  resultStage.classList.add("agent-running");
  $("#decision-section").classList.remove("hidden");
  renderRunSteps("running");
  renderChainLens();
  hidePurchasePopover();
  renderMarketScan("searching", null, query);
  showPendingPurchasePopover(query, budget, "scan");
  const progressTimers = [
    setTimeout(() => {
      renderRunSteps("choosing");
      renderMarketScan("searching", null, query);
      animateCoverage(28, 900);
      updatePurchasePopover(
        "Source policy",
        "Scoring candidate articles",
        "Paid previews are being compared against budget, relevance, and cache rules. No payment is sent during this step.",
        "policy: relevance / price / cache boundary",
        "Agent state",
      );
    }, 260),
    setTimeout(() => {
      renderRunSteps("settling");
      animateCoverage(58, 900);
      updatePurchasePopover(
        "Authorizing route",
        "Payment path is being selected",
        "If the source is new, Circle will move USDC. If it was already paid, Obol will reuse the prior receipt instead.",
        "route check: transfer or receipt reuse",
        "Agent state",
      );
    }, 620),
    setTimeout(() => {
      renderRunSteps("proving");
      animateCoverage(88, 1000);
      updatePurchasePopover(
        "Binding receipt",
        "Preparing final proof",
        "The console is binding the decision to a visible receipt: new Arc txHash, prior paid receipt, or a no-spend skip.",
        "proof check: txHash / cache / skip",
        "Proof state",
      );
    }, 1050),
  ];
  const clearProgressTimers = () => {
    progressTimers.forEach((timer) => clearTimeout(timer));
  };
  $("#r-plan").innerHTML = `<span class="loading">scoring sources, checking budget, and deciding what to buy...</span>`;
  $("#r-summary").innerHTML = "";
  $("#r-proof-grid").innerHTML = "";
  $("#r-policy").innerHTML = "";
  $("#r-stop-reason").textContent = "Policy engine is evaluating candidates.";
  $("#coverage-title").textContent = "Query Coverage";
  $("#coverage-note").textContent = "Scoring source relevance and budget fit.";
  $("#coverage-label").textContent = "0%";
  $("#coverage-bar").style.transform = "scaleX(0)";
  $("#r-decisions").innerHTML = "";
  $("#r-receipts").innerHTML = "";
  $("#r-answer").textContent = "";
  $("#r-confidence").textContent = "";

  try {
    const run = await api("/api/agent/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, budget_usdc: budget, policy }),
    });
    // A warm public demo can answer before the staged progress animation has
    // finished. Stop every pending stage before rendering the terminal state;
    // otherwise a late timer can overwrite "complete" with the 28% scoring
    // popover and cancel its auto-close timer.
    clearProgressTimers();
    renderRun(run);
    renderRunSteps(run.status === "pending" ? "settling" : run.status === "error" ? "idle" : "done");
    renderMarketScan("done", run, query);
    showPurchasePopover(run);
    btn.textContent = run.status === "pending"
      ? "Settlement pending"
      : run.status === "error"
        ? "Settlement failed"
        : (run.receipts || []).some(isSettledReceipt)
          ? "Purchased"
          : (run.saved_usdc > 0 ? "Reused receipt" : "Run complete");
    setTimeout(() => {
      if (!btn.disabled) btn.textContent = "Run agent";
    }, 1400);
    await Promise.all([loadStats(), currentCreatorId ? selectCreator(currentCreatorId) : Promise.resolve()]);
  } catch (e) {
    clearProgressTimers();
    $("#r-plan").innerHTML = `<span class="error">Error: ${esc(e.message)}</span>`;
    updatePurchasePopover(
      "Run failed",
      "Payment route unavailable",
      "The agent could not reach the local backend or settlement route. Start the backend and retry the run.",
      e.message,
      "Diagnostics",
    );
  } finally {
    clearProgressTimers();
    dashboard.classList.remove("is-running");
    resultStage.classList.remove("agent-running");
    btn.disabled = false;
    if (btn.textContent === "Agent deciding...") btn.textContent = "Run agent";
  }
}

function renderRun(run) {
  const coverage = Math.round((run.coverage || 0) * 100);
  const firstReceipt = (run.receipts || [])[0];
  const liveSettlement = isLiveReceipt(firstReceipt);
  const mockSettlement = isMockReceipt(firstReceipt);
  const pendingSettlement = isPendingReceipt(firstReceipt);
  const failedSettlement = isFailedReceipt(firstReceipt);
  const settledReceipt = isSettledReceipt(firstReceipt);
  const hasReusableSource = (run.decisions || []).some((d) => d.decision === "reuse");
  renderChainLens(run);
  $("#r-plan").textContent = run.plan || "";
  const policy = run.policy || {};
  const maxPrice = policy.max_price_usdc == null
    ? "budget only"
    : money(policy.max_price_usdc, 3);
  const maxPurchases = policy.max_purchases == null
    ? "unlimited"
    : policy.max_purchases;
  $("#r-policy").innerHTML = [
    ["Spendable", money(policy.spendable_budget_usdc ?? run.budget_usdc)],
    ["Protected", money(policy.reserve_usdc ?? 0)],
    ["Max / source", maxPrice],
    ["Min relevance", fmt(policy.min_relevance ?? 0.35, 2)],
    ["Max paid reads", maxPurchases],
  ].map(([label, value]) => `
    <article>
      <span>${esc(label)}</span>
      <strong>${esc(value)}</strong>
    </article>
  `).join("");
  $("#r-stop-reason").textContent = run.stop_reason || "Run completed under policy.";
  if (firstReceipt) {
    $("#coverage-title").textContent = "Settlement Progress";
    if (liveSettlement) {
      $("#coverage-note").textContent = `Answer coverage: ${coverage}%. Live Arc payment proof is complete.`;
      animateCoverage(100, 1600);
    } else if (mockSettlement) {
      $("#coverage-note").textContent = `Answer coverage: ${coverage}%. Simulated demo receipt is complete; no on-chain payment occurred.`;
      animateCoverage(100, 1600);
    } else if (pendingSettlement) {
      $("#coverage-note").textContent = "Circle has not reported COMPLETE. Funds are reserved and paid content remains locked.";
      animateCoverage(72, 900);
    } else if (failedSettlement) {
      $("#coverage-note").textContent = "Circle reported a terminal failure. No paid content was released.";
      animateCoverage(100, 900);
    } else {
      $("#coverage-note").textContent = "This legacy receipt is unverified and is not counted as a completed payment.";
      animateCoverage(100, 900);
    }
  } else if (hasReusableSource) {
    $("#coverage-title").textContent = "Receipt Reuse";
    $("#coverage-note").textContent = `Answer coverage: ${coverage}%. Prior paid receipt reused.`;
    animateCoverage(100, 1600);
  } else {
    $("#coverage-title").textContent = "Query Coverage";
    $("#coverage-note").textContent = "No settlement proof was needed for this run.";
    animateCoverage(coverage, 1600);
  }

  $("#r-summary").innerHTML = [
    ["spent", money(run.total_spent)],
    ["budget kept", money(run.budget_remaining)],
    ["sources used", run.sources_used],
    ["saved", money(run.saved_usdc)],
  ].map(([label, value]) => `
    <article class="metric">
      <div class="value">${value}</div>
      <div class="label">${label}</div>
    </article>
  `).join("");

  const decisionLabel = pendingSettlement
    ? "Content locked"
    : failedSettlement
      ? "Purchase rejected"
      : firstReceipt && settledReceipt
        ? "Read approved"
        : firstReceipt
          ? "Receipt unverified"
          : "No paid read needed";
  const settlementLabel = firstReceipt
    ? liveSettlement
      ? `${money(firstReceipt.amount_usdc)} paid through Circle Wallets`
      : mockSettlement
        ? `${money(firstReceipt.amount_usdc)} simulated in demo mode`
        : pendingSettlement
          ? `${money(firstReceipt.amount_usdc)} reserved pending COMPLETE`
          : failedSettlement
            ? `${money(firstReceipt.amount_usdc)} failed / not paid`
            : `${money(firstReceipt.amount_usdc)} unverified legacy record`
    : `${money(run.saved_usdc)} preserved by reuse`;
  const proofLabel = firstReceipt
    ? shortHash(firstReceipt.tx_hash || firstReceipt.transaction_id)
    : "cache proof";
  $("#r-proof-grid").innerHTML = [
    ["Decision", decisionLabel, "best priced source"],
    ["Settlement", settlementLabel,
      liveSettlement ? "Circle Wallets / Arc"
        : mockSettlement ? "Mock engine / no funds moved"
          : pendingSettlement ? "Awaiting Circle COMPLETE / no content"
            : failedSettlement ? "Terminal failure / excluded from totals"
              : "Unverified / excluded from totals"],
    ["Proof", proofLabel, firstReceipt
      ? (liveSettlement ? "Arc txHash confirmed"
        : mockSettlement ? "Simulated receipt / not on-chain"
          : pendingSettlement ? "Pending transaction claim"
            : failedSettlement ? "Failure record"
              : "Legacy record / not verified")
      : "No new transfer required"],
  ].map(([label, main, detail]) => `
    <article class="result-proof">
      <span>${esc(label)}</span>
      <strong>${esc(main)}</strong>
      <code>${esc(detail)}</code>
    </article>
  `).join("");

  const decisions = run.decisions || [];
  const visibleDecisions = decisions.slice(0, 8);
  const hiddenDecisionCount = Math.max(0, decisions.length - visibleDecisions.length);
  const stopEvent = (run.audit_log || []).filter((event) => event.event === "stop").slice(-1)[0];
  $("#r-decisions").innerHTML = visibleDecisions.map((d) => `
    <tr>
      <td><span class="badge ${esc(d.decision)}">${esc(d.decision)}</span></td>
      <td>${esc(d.title)}</td>
      <td class="muted">${esc(d.creator_name)}</td>
      <td class="rel-cell">${fmt(d.relevance, 2)}</td>
      <td class="price-cell">${money(d.price_usdc, 3)}</td>
      <td class="reason-cell"><code class="policy-rule">${esc(d.policy_rule || "legacy_decision")}</code>${esc(d.reason)}</td>
    </tr>
  `).join("") + (hiddenDecisionCount ? `
    <tr class="decision-summary-row">
      <td><span class="badge reuse">scan</span></td>
      <td colspan="5">${hiddenDecisionCount} additional sources were scored and collapsed after the agent found enough proof coverage.</td>
    </tr>
  ` : "") + (stopEvent ? `
    <tr class="policy-stop-row">
      <td><span class="badge stop">stop</span></td>
      <td>Policy engine</td>
      <td class="muted">—</td>
      <td class="rel-cell">—</td>
      <td class="price-cell">${money(0, 3)}</td>
      <td class="reason-cell"><code class="policy-rule">${esc(stopEvent.rule)}</code>${esc(stopEvent.reason)}</td>
    </tr>
  ` : "");

  const conf = run.confidence || "none";
  const pill = $("#r-confidence");
  pill.textContent = `confidence ${conf}`;
  pill.className = `pill ${conf === "high" ? "pill-ok" : conf === "none" ? "pill-muted" : "pill-warn"}`;

  $("#r-receipts").innerHTML = (run.receipts || []).length
    ? run.receipts.map((r) => `
      <article class="receipt">
        <span class="amt">${money(r.amount_usdc)}</span>
        <span class="to">${esc(r.creator_name)} / ${esc(r.title)}</span>
        <span class="tx">${esc(isLiveReceipt(r) ? r.blockchain : receiptModeLabel(r))} ${esc(shortHash(r.tx_hash || r.transaction_id))}</span>
      </article>
    `).join("")
    : `<p class="muted">No new payment was needed. The agent either reused cached reads or bought nothing.</p>`;

  $("#r-answer").textContent = run.answer || "";
}

function renderReceiptDrawer(row) {
  const drawer = $("#receipt-drawer");
  const title = $("#drawer-title");
  const body = $("#drawer-body");
  if (!drawer || !title || !body || !row) return;
  const live = isLiveReceipt(row);
  const mock = isMockReceipt(row);
  const pending = isPendingReceipt(row);
  const failed = isFailedReceipt(row);
  const stateCopy = live
    ? "confirmed on Arc Testnet"
    : mock
      ? "simulated demo receipt / not on-chain"
      : pending
        ? "pending / content locked / not counted as paid"
        : failed
          ? "failed / unpaid"
          : "unverified legacy record";
  title.textContent = publicReceiptTitle(row.title || "Payment receipt", row.creator_name);
  body.innerHTML = `
    <div class="drawer-amount">
      <span>${money(row.amount_usdc)}</span>
      <small>${esc(stateCopy)}</small>
    </div>
    <div class="receipt-detail-grid">
      <div><span>Creator</span><strong>${esc(row.creator_name)}</strong></div>
      <div><span>Source</span><strong>${esc(row.source || "agent")}</strong></div>
      <div><span>Network</span><strong>${esc(live ? row.blockchain : mock ? "SIMULATED / NOT ON-CHAIN" : "NOT CONFIRMED")}</strong></div>
      <div><span>Time</span><strong>${esc(shortTime(row.created_at))}</strong></div>
    </div>
    <div class="drawer-proof">
      <span>${live ? "TxHash" : mock ? "Demo proof id" : "Recorded proof"}</span>
      <code>${esc(row.tx_hash || row.transaction_id || receiptModeLabel(row))}</code>
    </div>
    <div class="drawer-proof">
      <span>${live ? "Circle transaction" : "Settlement mode"}</span>
      <code>${esc(live ? (row.transaction_id || "not available") : receiptModeLabel(row))}</code>
    </div>
  `;
  drawer.classList.remove("hidden");
}

async function loadMarket() {
  const grid = $("#market-grid");
  grid.innerHTML = `<p class="loading">loading sources...</p>`;
  try {
    articles = await api("/api/articles");
    renderMarket();
    fillArticleSelects();
  } catch (e) {
    grid.innerHTML = `<p class="error">${esc(e.message)}</p>`;
  }
}

function publicArticleTitle(article) {
  const title = article.title || "";
  if (!/^Live buyer top-up:/i.test(title)) return title;
  const topics = [
    "Arc fee predictability for autonomous research agents",
    "Creator revenue receipts for machine readers",
    "Circle wallet execution patterns on Arc Testnet",
    "Budget-aware content buying for agent APIs",
    "x402 retry flows for paid research sources",
    "USDC settlement notes for AI content markets",
    "Cache reuse boundaries for paid agent reads",
    "Pricing paid previews without subscriptions",
    "How agents decide when a source is worth buying",
    "Field notes on creator payouts from machine traffic",
  ];
  return topics[Number(article.id || 0) % topics.length];
}

function publicArticlePreview(article) {
  const preview = article.preview || article.summary || "";
  if (!/^Live buyer top-up:/i.test(article.title || "")) return preview;
  return `${article.creator_name} publishes a paid research note for agents that need verifiable Arc settlement, creator receipts, and a concrete reason to spend or skip.`;
}

function publicTagLabel(tag = "") {
  const clean = tag.trim().toLowerCase();
  const aliases = {
    "live-testnet": "live-testnet",
    "buyer-wallet": "wallet",
    "research-agents": "research",
    "stablecoins": "stable",
    "settlement": "settle",
    "creators": "creator",
    "payments": "pay",
    "receipts": "receipt",
    "budgeting": "budget",
    "citations": "cite",
  };
  return aliases[clean] || clean.slice(0, 12);
}

function publicReceiptTitle(title = "", creatorName = "") {
  if (!/^Live buyer top-up:/i.test(title)) return title;
  return creatorName
    ? `${creatorName} creator revenue proof`
    : "Creator revenue proof from paid agent reads";
}

function renderMarket() {
  const q = $("#market-search").value.trim().toLowerCase();
  const list = articles.filter((a) => {
    const haystack = `${publicArticleTitle(a)} ${a.title} ${a.tags || ""} ${a.summary || ""}`.toLowerCase();
    return !q || haystack.includes(q);
  });
  $("#market-grid").innerHTML = list.length ? list.map((a) => `
    <article class="article">
      <div class="article-top">
        <h3>${esc(publicArticleTitle(a))}</h3>
        <span class="lock">LOCKED</span>
      </div>
      <div class="by">by ${esc(a.creator_name)}</div>
      <div class="tag-row">
        ${(a.tags || "untagged").split(",").slice(0, 4).map((t) => `<span>${esc(publicTagLabel(t))}</span>`).join("")}
      </div>
      <p class="preview">${esc(publicArticlePreview(a))}</p>
      <div class="foot">
        <span class="price">${money(a.price_usdc, 3)} per read</span>
        <div class="article-actions">
          <button class="mini-action" data-market-action="agent" data-article-id="${a.id}" type="button">Ask AI</button>
          <button class="mini-action accent" data-market-action="unlock" data-article-id="${a.id}" type="button">Unlock</button>
        </div>
      </div>
      <p class="article-status" id="article-status-${a.id}"></p>
    </article>
  `).join("") : `<p class="muted">No matching sources.</p>`;
}

function articleQuery(article) {
  const tags = article.tags ? ` Tags: ${article.tags}.` : "";
  return `Evaluate whether this paid source is worth buying for an answer: ${publicArticleTitle(article)}. ${article.summary || article.preview || ""}${tags}`;
}

function analyzeArticleWithAgent(articleId) {
  const article = articles.find((a) => Number(a.id) === Number(articleId));
  if (!article) return;
  showView("console");
  clearRun();
  $("#q-input").value = articleQuery(article);
  $("#b-input").value = String(Math.max(0.011, Number(article.price_usdc || 0) + 0.002).toFixed(3));
  $("#empty-run").classList.add("hidden");
  $("#run-dashboard").classList.remove("hidden");
  $("#decision-section").classList.remove("hidden");
  renderMarketScan("searching", null, publicArticleTitle(article));
  $("#r-plan").innerHTML = `<span class="loading">Agent will compare this source against related paid articles before buying.</span>`;
  setTimeout(runAgent, 260);
}

async function unlockArticle(articleId) {
  const article = articles.find((a) => Number(a.id) === Number(articleId));
  if (!article) return;
  const button = $(`[data-market-action="unlock"][data-article-id="${articleId}"]`);
  const status = $(`#article-status-${articleId}`);
  let waitingTimer = null;
  if (button) {
    button.disabled = true;
    button.textContent = "Unlocking...";
  }
  showUnlockModal(article);
  if (status) {
    status.textContent = `Submitting ${money(article.price_usdc, 3)} USDC payment through Circle...`;
    status.className = "article-status is-pending";
  }
  waitingTimer = setTimeout(() => {
    if (status) status.textContent = "Circle is still confirming the Arc testnet transfer. This can take up to 45 seconds.";
    updateUnlockModal("settling");
  }, 7000);
  setTimeout(() => updateUnlockModal("settling"), 1200);
  try {
    const response = await rawApi(`/api/articles/${articleId}/unlock`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ buyer: "human-demo-user" }),
    });
    const res = response.body || {};
    if (waitingTimer) clearTimeout(waitingTimer);
    if (response.status === 202 || res.status === "settlement_pending" || isPendingReceipt(res.receipt)) {
      updateUnlockModal("pending", res);
      if (status) {
        status.textContent = "Circle confirmation is pending. No second transfer was sent and the source remains locked.";
        status.className = "article-status is-pending";
      }
      renderReceiptDrawer({
        ...res.receipt,
        title: res.title,
        creator_name: res.creator_name,
        amount_usdc: res.amount_paid_usdc ?? res.receipt?.amount_usdc,
        source: "human unlock",
        created_at: res.receipt?.created_at || Math.floor(Date.now() / 1000),
      });
      await loadStats();
      return;
    }
    if (!response.ok) {
      throw new Error(res.error || `${response.status} settlement request failed`);
    }
    updateUnlockModal("success", res);
    const live = isLiveReceipt(res.receipt);
    if (status) {
      status.textContent = live
        ? `Unlocked. ${res.creator_name} received ${money(res.amount_paid_usdc)}.`
        : `Unlocked in demo mode. ${money(res.amount_paid_usdc)} was simulated; no funds moved.`;
      status.className = "article-status is-ok";
    }
    renderReceiptDrawer({
      title: res.title,
      creator_name: res.creator_name,
      amount_usdc: res.amount_paid_usdc,
      tx_hash: res.receipt?.tx_hash,
      transaction_id: res.receipt?.transaction_id,
      blockchain: res.receipt?.blockchain || "ARC-TESTNET",
      settlement_mode: res.receipt?.settlement_mode || "mock",
      source: "human unlock",
      created_at: Math.floor(Date.now() / 1000),
    });
    await Promise.all([loadStats(), currentCreatorId ? selectCreator(currentCreatorId) : Promise.resolve()]);
  } catch (e) {
    if (waitingTimer) clearTimeout(waitingTimer);
    updateUnlockModal("error", { message: e.message });
    if (status) {
      status.textContent = `Unlock failed: ${e.message}`;
      status.className = "article-status is-error";
    }
    showToast(`Unlock failed: ${e.message}`, "error");
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "Unlock";
    }
  }
}

async function loadCreators() {
  const list = $("#creator-list");
  list.innerHTML = `<li class="loading">loading creators...</li>`;
  try {
    creators = await api("/api/creators");
    list.innerHTML = creators.map((c) => `
      <li data-cid="${c.id}">
        <strong>${esc(c.name)}</strong>
        <div class="addr">${esc(shortHash(c.payout_address))}</div>
      </li>
    `).join("");
    fillCreatorSelect();
    if (!currentCreatorId && creators[0]) currentCreatorId = creators[0].id;
    if (currentCreatorId) await selectCreator(currentCreatorId);
  } catch (e) {
    list.innerHTML = `<li class="error">${esc(e.message)}</li>`;
  }
}

function fillCreatorSelect() {
  const select = $("#article-creator");
  if (!select || !creators.length) return;
  select.innerHTML = creators.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("");
}

async function selectCreator(cid) {
  currentCreatorId = Number(cid);
  $$("#creator-list li").forEach((li) => li.classList.toggle("active", Number(li.dataset.cid) === currentCreatorId));
  const box = $("#creator-detail");
  box.innerHTML = `<p class="loading">loading earnings...</p>`;
  try {
    const d = await api(`/api/creators/${currentCreatorId}/earnings`);
    const latest = d.settled_payments && d.settled_payments.length
      ? d.settled_payments[0]
      : null;
    const unverifiedCount = (d.unverified_payments || []).length;
    box.innerHTML = `
      <div class="panel-head">
        <div>
          <span class="section-label">Creator wallet</span>
          <h3>${esc(d.creator.name)}</h3>
        </div>
        <span class="pill">${d.num_reads} live / ${d.demo_reads || 0} simulated reads</span>
      </div>
      <section class="creator-proof-lens">
        <article>
          <span>Total earned</span>
          <strong>${money(d.total_earned_usdc)}</strong>
          <p>Confirmed live USDC only${d.demo_reads ? ` / ${money(d.demo_volume_usdc)} simulated separately` : ""}${unverifiedCount ? ` / ${unverifiedCount} unverified excluded` : ""}</p>
        </article>
        <article>
          <span>Latest paid source</span>
          <strong>${latest ? esc(publicReceiptTitle(latest.title, d.creator.name)) : "waiting for first read"}</strong>
          <p>${latest ? esc(latest.source || "agent") : "no receipt yet"}</p>
        </article>
        <article>
          <span>Latest proof</span>
          <strong>${latest ? esc(shortHash(latest.tx_hash || latest.transaction_id)) : "no tx yet"}</strong>
          <p>${latest
            ? esc(isLiveReceipt(latest) ? (latest.blockchain || "ARC-TESTNET") : receiptModeLabel(latest))
            : "waiting for receipt"}</p>
        </article>
      </section>
      <div class="creator-payments">
        <span class="section-label">Payment history</span>
        ${d.payments.length ? d.payments.map((p) => `
          <div class="pay-row">
            <div class="pay-copy">
              <strong>${esc(publicReceiptTitle(p.title, d.creator.name))}</strong>
              <span>
                <em>${esc(p.source || "agent")}</em>
                <em>${receiptModeLabel(p)}</em>
                ${p.tx_hash ? `<code>${esc(shortHash(p.tx_hash))}</code>` : ""}
              </span>
            </div>
            <span class="amt">${isLiveReceipt(p) ? "+" : ""}${money(p.amount_usdc)}${isMockReceipt(p) ? " simulated" : isPendingReceipt(p) ? " reserved" : isFailedReceipt(p) ? " unpaid" : ""}</span>
          </div>
        `).join("") : `<p class="muted">No earnings yet. Run the agent or unlock through x402.</p>`}
      </div>
    `;
  } catch (e) {
    box.innerHTML = `<p class="error">${esc(e.message)}</p>`;
  }
}

async function createArticle(event) {
  event.preventDefault();
  showToast("");
  const body = {
    creator_id: Number($("#article-creator").value),
    title: $("#article-title").value.trim(),
    price_usdc: Number($("#article-price").value),
    tags: $("#article-tags").value.trim(),
    summary: $("#article-summary").value.trim(),
    content: $("#article-content").value.trim(),
  };
  try {
    const article = await api("/api/articles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    showToast(`Published source #${article.id}. It is now visible in the marketplace.`);
    await Promise.all([loadMarket(), loadStats(), loadX402Articles()]);
  } catch (e) {
    showToast(e.message, "error");
  }
}

function fillArticleSelects() {
  const opts = articles.map((a) => `<option value="${a.id}">${esc(publicArticleTitle(a))} (${money(a.price_usdc, 3)})</option>`).join("");
  const x402Select = $("#x402-article");
  if (x402Select) x402Select.innerHTML = opts;
}

async function loadX402Articles() {
  if (!articles.length) {
    try { articles = await api("/api/articles"); } catch (_) {}
  }
  fillArticleSelects();
}

async function getX402Challenge() {
  const id = $("#x402-article").value;
  const out = $("#x402-challenge");
  out.textContent = "requesting /x402/articles/" + id + "...";
  const res = await rawApi(`/x402/articles/${id}`);
  out.textContent = JSON.stringify({ http_status: res.status, ...res.body }, null, 2);
  if (res.body?.accepts?.[0]?.nonce) {
    $("#x402-proof").value = "0x" + res.body.accepts[0].nonce + "b".repeat(64 - res.body.accepts[0].nonce.length);
  }
}

async function payX402() {
  const id = $("#x402-article").value;
  const proof = $("#x402-proof").value.trim();
  const out = $("#x402-unlocked");
  out.textContent = "retrying with X-Payment...";
  const res = await rawApi(`/x402/articles/${id}`, {
    headers: { "X-Payment": proof, "X-Payer": "demo-agent" },
  });
  out.textContent = JSON.stringify({ http_status: res.status, ...res.body }, null, 2);
  await Promise.all([loadStats(), currentCreatorId ? selectCreator(currentCreatorId) : Promise.resolve()]);
}

async function loadTraction() {
  const runsBox = $("#recent-runs");
  const ledgerBox = $("#ledger-list");
  loadSettlementStatus();
  runsBox.innerHTML = `<p class="loading">loading runs...</p>`;
  ledgerBox.innerHTML = `<p class="loading">loading ledger...</p>`;
  try {
    const [runs, ledger, stats] = await Promise.all([
      api("/api/agent/runs"),
      api("/api/ledger"),
      api("/api/stats"),
    ]);
    $("#traction-runs").textContent = stats.num_runs;
    $("#traction-receipts").textContent = stats.total_reads;
    $("#traction-paid").textContent = money(stats.total_paid_usdc);
    $("#traction-saved").textContent = money(stats.usdc_saved_by_reuse);
    latestLedger = ledger;
    runsBox.innerHTML = runs.length ? runs.slice(0, 8).map((r) => `
      <article class="agent-activity">
        <div>
          <span>Run #${r.id} / budget ${money(r.budget_usdc)}</span>
          <p>${esc(r.query)}</p>
        </div>
        <strong>${money(r.total_spent)} ${r.status === "pending" ? "reserved" : "spent"}</strong>
      </article>
    `).join("") : `<p class="muted">No agent runs yet. Run the Agent Console first.</p>`;

    ledgerBox.innerHTML = ledger.length ? `
      <table class="ledger-table">
        <thead>
          <tr>
            <th>Time</th>
            <th>Agent</th>
            <th>Creator</th>
            <th>Content</th>
            <th>Amount</th>
            <th>Status</th>
            <th>TxHash</th>
            <th>Proof</th>
          </tr>
        </thead>
        <tbody>
          ${ledger.slice(0, 10).map((r, index) => `
            <tr id="tx-${esc(r.tx_hash || r.transaction_id || r.id)}" data-ledger-index="${index}">
              <td>${esc(shortTime(r.created_at))}</td>
              <td>${esc(r.source || "agent")}</td>
              <td>${esc(r.creator_name)}</td>
              <td>${esc(publicReceiptTitle(r.title, r.creator_name))}</td>
              <td class="amount-cell">${money(r.amount_usdc)}</td>
              <td><span class="status-pill">${esc(receiptModeLabel(r))}</span></td>
              <td class="hash-cell">${esc(shortHash(r.tx_hash || r.transaction_id))}</td>
              <td><button class="mini-action view-proof" type="button">View</button></td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    ` : `<p class="muted">No receipts yet. Run the agent or x402 flow.</p>`;
    ledgerBox.onclick = (event) => {
      const row = event.target.closest("tr[data-ledger-index]");
      if (!row) return;
      renderReceiptDrawer(latestLedger[Number(row.dataset.ledgerIndex)]);
    };
  } catch (e) {
    runsBox.innerHTML = `<p class="error">${esc(e.message)}</p>`;
    ledgerBox.innerHTML = `<p class="error">${esc(e.message)}</p>`;
  }
}

async function loadSettlementStatus() {
  const box = $("#settlement-status");
  const pill = $("#settlement-readiness-pill");
  if (!box || !pill) return;
  box.innerHTML = `<p class="loading">checking settlement...</p>`;
  try {
    const s = await api("/api/settlement/status");
    const ready = s.ready_for_live_transfers;
    pill.textContent = ready ? "live ready" : "mock / not live";
    pill.className = `pill ${ready ? "pill-ok" : "pill-warn"}`;
    box.innerHTML = `
      <div class="settlement-grid">
        <div><span>mode</span><strong>${esc(s.mode)}</strong></div>
        <div><span>chain</span><strong>${esc(s.blockchain)}</strong></div>
        <div><span>wallet</span><strong>${s.has_agent_wallet_id ? "configured" : "missing"}</strong></div>
        <div><span>crypto lib</span><strong>${s.cryptography_installed ? "installed" : "missing"}</strong></div>
      </div>
      ${s.missing.length ? `<p class="muted">Missing for real Arc testnet settlement: ${esc(s.missing.join(", "))}</p>` : `<p class="muted">Live Circle/Arc transfers are configured.</p>`}
    `;
  } catch (e) {
    pill.textContent = "check failed";
    pill.className = "pill pill-muted";
    box.innerHTML = `<p class="error">${esc(e.message)}</p>`;
  }
}

function initCinematicMotion() {
  const surfaceSelector = [
    ".stat",
    ".article",
    ".panel",
    ".run-panel",
    ".result-stage",
    ".proof-card",
    ".command-deck article",
    ".proof-grid article",
    ".demo-director article",
    ".proof-metrics article",
    ".persona-strip article",
    ".evaluation-lab article",
    ".creator-list li",
    ".chain-lens article",
    ".scan-lane article",
    ".result-proof-grid article",
    ".metric-row article",
  ].join(",");
  const revealSelector = [
    ".view-head",
    ".console-layout",
    ".creator-studio",
    ".x402-grid",
    ".traction-grid",
    ".market-grid .article",
    ".proof-metrics article",
    ".persona-strip article",
    ".command-deck article",
    ".proof-grid article",
    ".demo-director article",
    ".stat",
  ].join(",");
  const observed = new WeakSet();
  const io = "IntersectionObserver" in window
    ? new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("reveal-in");
            io.unobserve(entry.target);
          }
        });
      }, { rootMargin: "0px 0px -8% 0px", threshold: 0.12 })
    : null;

  const registerMotionTargets = () => {
    $$(surfaceSelector).forEach((el) => el.classList.add("motion-surface"));
    if (!io) {
      $$(revealSelector).forEach((el) => el.classList.add("reveal-in"));
      return;
    }
    $$(revealSelector).forEach((el) => {
      if (observed.has(el) || el.classList.contains("reveal-in")) return;
      observed.add(el);
      io.observe(el);
    });
  };

  let motionFrame = 0;
  let cursorX = window.innerWidth / 2;
  let cursorY = window.innerHeight / 2;
  document.addEventListener("pointermove", (event) => {
    cursorX = event.clientX;
    cursorY = event.clientY;
    const surface = event.target?.closest?.(".motion-surface");
    if (motionFrame) cancelAnimationFrame(motionFrame);
    motionFrame = requestAnimationFrame(() => {
      document.documentElement.style.setProperty("--cursor-x", `${cursorX}px`);
      document.documentElement.style.setProperty("--cursor-y", `${cursorY}px`);
      if (surface) {
        const rect = surface.getBoundingClientRect();
        surface.style.setProperty("--mx", `${cursorX - rect.left}px`);
        surface.style.setProperty("--my", `${cursorY - rect.top}px`);
      }
      motionFrame = 0;
    });
  }, { passive: true });

  const observer = new MutationObserver(() => requestAnimationFrame(registerMotionTargets));
  observer.observe(document.querySelector("main"), { childList: true, subtree: true });
  requestAnimationFrame(() => {
    document.body.classList.add("motion-ready");
    registerMotionTargets();
  });
}

function init() {
  $("#api-base").textContent = `API ${API}`;
  $("#api-base").addEventListener("click", () => {
    const value = prompt("Backend API base URL:", API);
    if (value) {
      localStorage.setItem("obol_api", value.trim());
      location.reload();
    }
  });

  document.addEventListener("click", (e) => {
    const nav = e.target.closest("[data-view]");
    if (nav) {
      e.preventDefault();
      showView(nav.dataset.view);
    }
  });

  $("#run-btn").addEventListener("click", runAgent);
  $("#demo-path-btn").addEventListener("click", () => primeLiveDemo(true));
  $("#topbar-demo-btn").addEventListener("click", () => primeLiveDemo(true));
  $("#quick-demo-btn").addEventListener("click", () => primeLiveDemo(true));
  $("#reset-demo-btn").addEventListener("click", resetDemoData);
  $("#q-input").addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") runAgent();
  });
  $$(".chip").forEach((chip) => chip.addEventListener("click", () => {
    $("#q-input").value = chip.dataset.q;
    $("#b-input").value = chip.dataset.b;
    runAgent();
  }));
  $("#market-search").addEventListener("input", renderMarket);
  $("#market-grid").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-market-action]");
    if (!btn) return;
    const id = btn.dataset.articleId;
    if (btn.dataset.marketAction === "agent") analyzeArticleWithAgent(id);
    if (btn.dataset.marketAction === "unlock") unlockArticle(id);
  });
  $("#creator-list").addEventListener("click", (e) => {
    const li = e.target.closest("li[data-cid]");
    if (li) selectCreator(li.dataset.cid);
  });
  $("#article-form").addEventListener("submit", createArticle);
  $("#x402-challenge-btn").addEventListener("click", getX402Challenge);
  $("#x402-pay-btn").addEventListener("click", payX402);
  $("#refresh-traction-btn").addEventListener("click", loadTraction);
  $("#drawer-close")?.addEventListener("click", () => $("#receipt-drawer")?.classList.add("hidden"));
  $("#purchase-close")?.addEventListener("click", hidePurchasePopover);
  $("#unlock-close")?.addEventListener("click", hideUnlockModal);
  initCinematicMotion();

  loadHealth();
  renderMarketScan("idle");
  loadStats();
  loadEvaluationEvidence();
  updateDaemonDeck();
  loadMarket();
  loadCreators();
  if (dashboardPoll) clearInterval(dashboardPoll);
  dashboardPoll = setInterval(refreshVisibleDashboard, 30000);
  setTimeout(applyRecordingScene, 500);
}

init();

async function replayRunForRecording(runId, mode = "success") {
  const run = await api(`/api/agent/runs/${runId}`);
  showView("console");
  $("#q-input").value = run.query;
  $("#b-input").value = run.budget_usdc;
  if (run.policy) {
    $("#policy-reserve").value = run.policy.reserve_usdc ?? 0;
    $("#policy-max-price").value = run.policy.max_price_usdc ?? run.budget_usdc;
    $("#policy-min-relevance").value = run.policy.min_relevance ?? 0.35;
    $("#policy-max-purchases").value = run.policy.max_purchases ?? 99;
  }
  $("#empty-run").classList.add("hidden");
  $("#run-dashboard").classList.remove("hidden");
  $("#decision-section").classList.remove("hidden");
  renderRun(run);
  renderRunSteps(run.status === "pending" ? "settling" : run.status === "error" ? "idle" : "done");
  renderMarketScan("done", run, run.query);
  setCoverageNow(run.status === "pending" ? 72 : 100);
  showPurchasePopover(run);
  if (mode === "decision") {
    hidePurchasePopover();
    scrollToWithTopbar("#decision-section");
  }
}

async function applyRecordingScene() {
  const params = new URLSearchParams(location.search);
  const hashParts = location.hash.replace(/^#/, "").split("/").filter(Boolean);
  const scene = params.get("scene") || hashParts[0];
  if (!scene) return;
  const runId = params.get("run") || hashParts[1];
  if (scene === "home") {
    showView("home");
    await loadStats();
    return;
  }
  if (scene === "proof") {
    showView("home");
    await loadStats();
    $("#live-proof")?.scrollIntoView({ block: "center" });
    return;
  }
  if (scene === "console-setup") {
    showView("console");
    $("#q-input").value = "Designing x402 endpoints for AI buyers";
    $("#b-input").value = "0.013";
    return;
  }
  if (scene === "console-pending") {
    showView("console");
    const query = "Designing x402 endpoints for AI buyers";
    const budget = 0.013;
    $("#q-input").value = query;
    $("#b-input").value = budget;
    $("#empty-run").classList.add("hidden");
    $("#run-dashboard").classList.remove("hidden");
    $("#run-dashboard").classList.add("is-running");
    $("#run-result").classList.add("agent-running");
    renderRunSteps("proving");
    renderChainLens();
    renderMarketScan("searching", null, query);
    setCoverageNow(88);
    updatePurchasePopover(
      "Proof check",
      "Preparing final proof",
      "The agent has ranked paid sources and is binding the decision to a visible receipt state.",
      "proof check: txHash or reusable receipt",
      "Agent state",
    );
    return;
  }
  if (scene === "console-success" && runId) {
    await replayRunForRecording(runId, "success");
    return;
  }
  if (scene === "decision-log" && runId) {
    await replayRunForRecording(runId, "decision");
    return;
  }
  if (scene === "market") {
    showView("market");
    await loadMarket();
    return;
  }
  if (scene === "x402") {
    showView("x402");
    await loadX402Articles();
    return;
  }
  if (scene === "traction") {
    showView("traction");
    await loadTraction();
    if (latestLedger[0]) renderReceiptDrawer(latestLedger[0]);
    return;
  }
  if (scene === "creators") {
    showView("creators");
    await loadCreators();
  }
}

window.applyRecordingScene = applyRecordingScene;


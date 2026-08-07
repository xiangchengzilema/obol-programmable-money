import React from "react";
import {
  AbsoluteFill,
  Audio,
  Composition,
  Sequence,
  Video,
  interpolate,
  registerRoot,
  staticFile,
  useCurrentFrame,
} from "remotion";

const FPS = 30;
const WIDTH = 1600;
const HEIGHT = 900;
const DURATION = 99 * FPS;
const OLD_PLATE_OFFSET_FRAMES = 127;

const timeline = [
  {
    id: "01",
    start: 0,
    end: 8,
    label: "PROBLEM",
    text: "AI agents already read creator work, research posts, and paid knowledge sources. But most machine reads create no revenue for the people who produced the work.",
    accent: "AI reads do not pay",
    visual: "new",
  },
  {
    id: "02",
    start: 8,
    end: 15.5,
    label: "FRESH ARC EVIDENCE",
    text: "Obol binds a current-repository agent decision to a completed Circle transfer and verifies payer, token, recipient, amount, transaction hash, and block on Arc Testnet.",
    accent: "strict USDC proof",
    visual: "new",
  },
  {
    id: "03",
    start: 15.5,
    end: 23,
    label: "AGENT BUYER",
    text: "The buyer is not a human clicking subscribe. It is an autonomous research agent with a question, a budget, and a payment policy.",
    accent: "budgeted agent",
    visual: "new",
  },
  {
    id: "04",
    start: 23,
    end: 32.5,
    label: "SOURCE SELECTION",
    text: "Before any USDC moves, the agent evaluates sources, scores relevance, compares prices, checks cache reuse, and protects the remaining budget.",
    accent: "score / price / cache",
    visual: "new",
  },
  {
    id: "05",
    start: 32.5,
    end: 42,
    label: "SAFE JUDGE DEMO",
    text: "The anonymous playground is deliberately forced mock and labels its receipt as simulated. Paid content is released only for a confirmed live receipt or an explicit mock demo receipt.",
    accent: "mock is never called live",
    visual: "safety",
  },
  {
    id: "06",
    start: 42,
    end: 50,
    label: "AUDIT LOG",
    text: "The decision log explains why the agent bought one source, skipped others, or reused a previous paid read.",
    accent: "explain every decision",
    visual: "decision",
  },
  {
    id: "07",
    start: 50,
    end: 59,
    label: "MARKETPLACE",
    text: "In the marketplace, creators publish paid research with public previews. Full content stays locked until a valid payment is attached.",
    accent: "locked until paid",
    visual: "old",
    disclosure: "DEMO CATALOG / SAMPLE DATA",
  },
  {
    id: "08",
    start: 59,
    end: 68,
    label: "CREATOR SIDE",
    text: "Creator Studio separates confirmed live earnings from simulated demo volume, pending attempts, and failed transfers, with an independent receipt trail for each creator.",
    accent: "honest creator accounting",
    visual: "new",
  },
  {
    id: "09",
    start: 68,
    end: 79,
    label: "X402 ACCESS",
    text: "For external agents, Obol exposes the same market through an x402 style HTTP payment flow: request, receive a 402 challenge, attach payment proof, and unlock the resource.",
    accent: "402 challenge -> proof",
    visual: "new",
  },
  {
    id: "10",
    start: 79,
    end: 91,
    label: "THIS ITERATION",
    text: "Obol began before this hackathon. This iteration added programmable spend guards, strict Arc proof verification, concurrency-safe payment claims, honest settlement states, and forty-six passing backend tests.",
    accent: "existing project / substantial new work",
    visual: "iteration",
  },
  {
    id: "11",
    start: 91,
    end: 99,
    label: "CLOSING",
    text: "Obol makes machine reading accountable: agents choose sources, Circle settles USDC, Arc verifies the transfer, and creators get paid.",
    accent: "chain-verifiable payments",
    visual: "new",
  },
];

const mono = "JetBrains Mono, SFMono-Regular, Menlo, Consolas, monospace";
const sans = "Inter, Arial, sans-serif";

function currentSegment(frame) {
  const seconds = frame / FPS;
  return timeline.find((item) => seconds >= item.start && seconds < item.end) ?? timeline[timeline.length - 1];
}

function easeIn(local, delay = 0) {
  return interpolate(local, [delay, delay + 14], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
}

function EvidenceBackground({ children }) {
  const frame = useCurrentFrame();
  const drift = interpolate(frame, [0, 360], [-80, 100], {
    extrapolateLeft: "extend",
    extrapolateRight: "extend",
  });
  return (
    <AbsoluteFill
      style={{
        overflow: "hidden",
        background:
          "radial-gradient(circle at 78% 18%, rgba(69, 223, 196, .17), transparent 31%), radial-gradient(circle at 18% 78%, rgba(59, 130, 246, .18), transparent 32%), #06111a",
        color: "#f5fbfa",
        fontFamily: sans,
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: -120,
          transform: `translateX(${drift}px) rotate(-7deg)`,
          opacity: 0.2,
          backgroundImage:
            "linear-gradient(rgba(103, 232, 211, .18) 1px, transparent 1px), linear-gradient(90deg, rgba(103, 232, 211, .18) 1px, transparent 1px)",
          backgroundSize: "78px 78px",
        }}
      />
      {children}
    </AbsoluteFill>
  );
}

function SafetySlate() {
  const frame = useCurrentFrame();
  const left = easeIn(frame, 2);
  const right = easeIn(frame, 12);
  return (
    <EvidenceBackground>
      <div style={{ position: "absolute", left: 84, top: 205, width: 620, opacity: left, transform: `translateY(${(1 - left) * 24}px)` }}>
        <div style={{ color: "#f3cb62", fontFamily: mono, fontWeight: 900, fontSize: 19, letterSpacing: 2.2 }}>
          HOSTED JUDGE PATH
        </div>
        <div style={{ marginTop: 20, fontSize: 60, lineHeight: 1.02, fontWeight: 900, letterSpacing: -2.5 }}>
          A mock receipt is
          <br />
          <span style={{ color: "#67e8d3" }}>never called live.</span>
        </div>
        <div style={{ marginTop: 25, color: "#b9c8cc", fontSize: 25, lineHeight: 1.42, maxWidth: 590 }}>
          The public playground is intentionally isolated from settlement credentials and marks every demo receipt explicitly.
        </div>
      </div>
      <div
        style={{
          position: "absolute",
          right: 86,
          top: 186,
          width: 690,
          height: 455,
          borderRadius: 28,
          padding: 34,
          opacity: right,
          transform: `translateX(${(1 - right) * 30}px)`,
          background: "rgba(11, 26, 38, .88)",
          border: "1px solid rgba(103, 232, 211, .36)",
          boxShadow: "0 30px 90px rgba(0,0,0,.42)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ color: "#d7e7e6", fontFamily: mono, fontSize: 18, fontWeight: 900 }}>PUBLIC PLAYGROUND</div>
          <div style={{ padding: "9px 14px", borderRadius: 999, border: "1px solid #67e8d3", color: "#67e8d3", fontFamily: mono, fontWeight: 900 }}>
            FORCED MOCK
          </div>
        </div>
        <div style={{ marginTop: 28, padding: 24, borderRadius: 18, background: "#061018", border: "1px solid rgba(255,255,255,.08)", fontFamily: mono, fontSize: 22, lineHeight: 1.65 }}>
          <div><span style={{ color: "#8ea3aa" }}>payment_mode:</span> <span style={{ color: "#67e8d3" }}>"mock"</span></div>
          <div><span style={{ color: "#8ea3aa" }}>settlement:</span> <span style={{ color: "#67e8d3" }}>"simulated"</span></div>
          <div><span style={{ color: "#8ea3aa" }}>funds_moved:</span> <span style={{ color: "#f3cb62" }}>false</span></div>
        </div>
        <div style={{ marginTop: 24, display: "grid", gridTemplateColumns: "1fr auto 1fr", alignItems: "center", gap: 16 }}>
          <div style={{ padding: "20px", borderRadius: 16, background: "rgba(103,232,211,.08)", color: "#d9efeb", fontWeight: 800, fontSize: 20 }}>
            Confirmed live receipt
          </div>
          <div style={{ color: "#80959b", fontFamily: mono, fontWeight: 900 }}>OR</div>
          <div style={{ padding: "20px", borderRadius: 16, background: "rgba(243,203,98,.08)", color: "#f2daa0", fontWeight: 800, fontSize: 20 }}>
            Explicit mock demo receipt
          </div>
        </div>
        <div style={{ marginTop: 18, color: "#9fb2b6", fontFamily: mono, fontSize: 16 }}>UNLOCK GATE · rejects ambiguous settlement state</div>
      </div>
    </EvidenceBackground>
  );
}

function DecisionRow({ tone, action, source, reason, delay }) {
  const frame = useCurrentFrame();
  const p = easeIn(frame, delay);
  const colors = tone === "buy" ? ["#67e8d3", "rgba(103,232,211,.10)"] : tone === "reuse" ? ["#66b8ff", "rgba(102,184,255,.10)"] : ["#ff7b86", "rgba(255,123,134,.09)"];
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "120px 1.15fr 1.5fr",
        gap: 22,
        alignItems: "center",
        padding: "19px 24px",
        borderRadius: 18,
        background: colors[1],
        border: `1px solid ${colors[0]}55`,
        opacity: p,
        transform: `translateX(${(1 - p) * 34}px)`,
      }}
    >
      <div style={{ color: colors[0], fontFamily: mono, fontWeight: 900, fontSize: 19 }}>{action}</div>
      <div style={{ color: "#f5fbfa", fontWeight: 850, fontSize: 22 }}>{source}</div>
      <div style={{ color: "#b8c9cc", fontSize: 19, lineHeight: 1.35 }}>{reason}</div>
    </div>
  );
}

function DecisionSlate() {
  const frame = useCurrentFrame();
  const p = easeIn(frame, 1);
  return (
    <EvidenceBackground>
      <div style={{ position: "absolute", left: 84, right: 84, top: 185, opacity: p }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "end" }}>
          <div>
            <div style={{ color: "#f3cb62", fontFamily: mono, fontWeight: 900, fontSize: 18, letterSpacing: 2 }}>DECISION TRACE</div>
            <div style={{ marginTop: 12, fontWeight: 900, fontSize: 54, letterSpacing: -2 }}>Every outcome has a reason.</div>
          </div>
          <div style={{ color: "#9eb0b5", fontFamily: mono, fontSize: 17 }}>POLICY · PRICE · RELEVANCE · CACHE</div>
        </div>
        <div style={{ marginTop: 28, display: "grid", gap: 14 }}>
          <DecisionRow tone="buy" action="BUY" source="Best matching paid source" reason="Meets relevance threshold and price guard" delay={8} />
          <DecisionRow tone="skip" action="SKIP" source="Lower relevance source" reason="Below programmable minimum; no payment needed" delay={18} />
          <DecisionRow tone="reuse" action="REUSE" source="Previously paid read" reason="Valid cached receipt; budget preserved" delay={28} />
        </div>
        <div style={{ marginTop: 22, padding: "18px 24px", borderRadius: 16, background: "rgba(6,16,24,.84)", border: "1px solid rgba(255,255,255,.10)", color: "#c5d4d6", fontFamily: mono, fontSize: 18 }}>
          AUDITABLE OUTPUT · source + decision + rule + receipt reference
        </div>
      </div>
    </EvidenceBackground>
  );
}

function IterationSlate() {
  const frame = useCurrentFrame();
  const p = easeIn(frame, 2);
  const list = [
    "Programmable spend guards",
    "Strict Arc proof verification",
    "Concurrency-safe payment claims",
    "Honest settlement states",
  ];
  return (
    <EvidenceBackground>
      <div style={{ position: "absolute", left: 84, right: 84, top: 174, display: "grid", gridTemplateColumns: "1.18fr .82fr", gap: 48, opacity: p }}>
        <div>
          <div style={{ color: "#f3cb62", fontFamily: mono, fontWeight: 900, fontSize: 18, letterSpacing: 2.2 }}>THIS HACKATHON ITERATION</div>
          <div style={{ marginTop: 16, fontSize: 58, lineHeight: 1.04, fontWeight: 900, letterSpacing: -2.5 }}>
            Existing project.
            <br />
            <span style={{ color: "#67e8d3" }}>Substantial new work.</span>
          </div>
          <div style={{ marginTop: 28, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
            {list.map((item, index) => {
              const itemProgress = easeIn(frame, 12 + index * 7);
              return (
                <div
                  key={item}
                  style={{
                    minHeight: 88,
                    display: "flex",
                    alignItems: "center",
                    gap: 16,
                    padding: "18px 20px",
                    borderRadius: 18,
                    background: "rgba(15,34,47,.84)",
                    border: "1px solid rgba(103,232,211,.22)",
                    opacity: itemProgress,
                    transform: `translateY(${(1 - itemProgress) * 18}px)`,
                    color: "#dbe9e8",
                    fontSize: 21,
                    fontWeight: 800,
                  }}
                >
                  <span style={{ color: "#67e8d3", fontFamily: mono, fontWeight: 900 }}>✓</span>
                  {item}
                </div>
              );
            })}
          </div>
        </div>
        <div style={{ padding: 34, borderRadius: 30, background: "rgba(8,22,32,.91)", border: "1px solid rgba(103,232,211,.38)", boxShadow: "0 30px 90px rgba(0,0,0,.42)" }}>
          <div style={{ color: "#a9bdc1", fontFamily: mono, fontWeight: 900, fontSize: 18 }}>BACKEND TEST EVIDENCE</div>
          <div style={{ marginTop: 20, display: "flex", alignItems: "baseline", gap: 14 }}>
            <span style={{ color: "#67e8d3", fontFamily: mono, fontSize: 104, lineHeight: 1, fontWeight: 900, letterSpacing: -7 }}>46</span>
            <span style={{ color: "#eaf4f3", fontFamily: mono, fontSize: 30, fontWeight: 900 }}>/ 46</span>
          </div>
          <div style={{ marginTop: 8, color: "#f3cb62", fontSize: 27, fontWeight: 900 }}>PASSING</div>
          <div style={{ marginTop: 28, padding: 22, borderRadius: 17, background: "#030b11", border: "1px solid rgba(255,255,255,.09)", color: "#b9f4e8", fontFamily: mono, fontSize: 17, lineHeight: 1.55 }}>
            ..............................................<br />
            <span style={{ color: "#67e8d3" }}>[100%] 46 passed</span>
          </div>
          <div style={{ marginTop: 22, color: "#a7b9bd", fontSize: 18, lineHeight: 1.42 }}>
            Verified against the current repository before final render.
          </div>
        </div>
      </div>
    </EvidenceBackground>
  );
}

function Disclosure({ text }) {
  return (
    <div
      style={{
        position: "absolute",
        right: 197,
        top: 31,
        width: 242,
        height: 49,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        borderRadius: 999,
        border: "1px solid rgba(103,232,211,.48)",
        background: "rgba(4,15,23,.97)",
        color: "#67e8d3",
        fontFamily: mono,
        fontSize: 13,
        fontWeight: 900,
        boxShadow: "0 10px 35px rgba(0,0,0,.36)",
      }}
    >
      {text}
    </div>
  );
}

function ClosingClaimPatch() {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [66, 80], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <div
      style={{
        position: "absolute",
        left: 310,
        top: 360,
        width: 980,
        height: 245,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        borderRadius: 24,
        opacity,
        background: "linear-gradient(110deg, rgba(19,13,31,.98), rgba(3,27,29,.98))",
        border: "1px solid rgba(103,232,211,.20)",
        boxShadow: "0 24px 80px rgba(0,0,0,.38)",
      }}
    >
      <div
        style={{
          color: "#f7fbf8",
          fontFamily: sans,
          fontSize: 55,
          lineHeight: 1.02,
          fontWeight: 900,
          letterSpacing: -1.5,
          textAlign: "center",
        }}
      >
        Agents choose sources.
        <br />
        Circle settles USDC.
        <br />
        <span style={{ color: "#67e8d3" }}>Arc verifies the transfer.</span>
      </div>
    </div>
  );
}

function VisualTrack() {
  return timeline.map((segment) => {
    const from = Math.round(segment.start * FPS);
    const durationInFrames = Math.round((segment.end - segment.start) * FPS);
    if (segment.visual === "safety") {
      return <Sequence key={segment.id} from={from} durationInFrames={durationInFrames}><SafetySlate /></Sequence>;
    }
    if (segment.visual === "decision") {
      return <Sequence key={segment.id} from={from} durationInFrames={durationInFrames}><DecisionSlate /></Sequence>;
    }
    if (segment.visual === "iteration") {
      return <Sequence key={segment.id} from={from} durationInFrames={durationInFrames}><IterationSlate /></Sequence>;
    }
    const old = segment.visual === "old";
    const startFrom = from + (old ? OLD_PLATE_OFFSET_FRAMES : 0);
    return (
      <Sequence key={segment.id} from={from} durationInFrames={durationInFrames}>
        <Video
          muted
          playbackRate={old ? 0.75 : 1}
          src={staticFile(old ? "obol_demo_v23_old_raw_plate.mp4" : "obol_demo_v23_raw_plate.mp4")}
          startFrom={startFrom}
        />
        {segment.disclosure ? <Disclosure text={segment.disclosure} /> : null}
        {segment.id === "11" ? <ClosingClaimPatch /> : null}
      </Sequence>
    );
  });
}

function Keyword({ segment }) {
  const frame = useCurrentFrame();
  const local = frame - segment.start * FPS;
  const total = (segment.end - segment.start) * FPS;
  const opacity = interpolate(local, [0, 12, total - 14, total], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const y = interpolate(local, [0, 18], [12, 0], { extrapolateRight: "clamp" });
  return (
    <div
      style={{
        position: "absolute",
        left: 48,
        top: 110,
        transform: `translateY(${y}px)`,
        opacity,
        display: "flex",
        alignItems: "center",
        gap: 14,
        padding: "12px 18px",
        borderRadius: 999,
        border: "1px solid rgba(103,232,211,.34)",
        background: "rgba(7,20,28,.82)",
        color: "#69f4d6",
        fontFamily: mono,
        fontSize: 18,
        fontWeight: 900,
        boxShadow: "0 20px 60px rgba(0,0,0,.36)",
      }}
    >
      <span style={{ color: "#f2ce63" }}>{segment.id}</span>
      <span>{segment.label}</span>
      <span style={{ color: "#d6e4e2", fontWeight: 800 }}>{segment.accent}</span>
    </div>
  );
}

function Subtitle({ segment }) {
  const frame = useCurrentFrame();
  const local = frame - segment.start * FPS;
  const total = (segment.end - segment.start) * FPS;
  const opacity = interpolate(local, [0, 10, total - 10, total], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const y = interpolate(local, [0, 14], [18, 0], { extrapolateRight: "clamp" });
  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        bottom: 0,
        minHeight: 132,
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        padding: "24px 92px",
        background: "linear-gradient(180deg, rgba(5,13,20,.62), rgba(5,13,20,.96))",
        borderTop: "1px solid rgba(103,232,211,.22)",
        opacity,
      }}
    >
      <div
        style={{
          transform: `translateY(${y}px)`,
          color: "#f7fbf8",
          fontFamily: sans,
          fontSize: 30,
          lineHeight: 1.22,
          fontWeight: 900,
          textAlign: "center",
          maxWidth: 1320,
          textShadow: "0 3px 16px rgba(0,0,0,.48)",
        }}
      >
        {segment.text}
      </div>
    </div>
  );
}

function ProgressRail() {
  const frame = useCurrentFrame();
  const progress = frame / DURATION;
  return (
    <div style={{ position: "absolute", left: 48, right: 48, bottom: 138, height: 4, borderRadius: 999, background: "rgba(255,255,255,.10)", overflow: "hidden" }}>
      <div style={{ width: `${Math.min(100, progress * 100)}%`, height: "100%", background: "linear-gradient(90deg, #5cefd0, #56b1ff, #ff4fd8)" }} />
    </div>
  );
}

function ObolFinalHybrid() {
  const frame = useCurrentFrame();
  const segment = currentSegment(frame);
  return (
    <AbsoluteFill style={{ backgroundColor: "#05090a" }}>
      <VisualTrack />
      <Audio src={staticFile("obol_v23_edge_voiceover.wav")} />
      <Keyword segment={segment} />
      <ProgressRail />
      <Subtitle segment={segment} />
    </AbsoluteFill>
  );
}

function Root() {
  return (
    <Composition
      id="ObolFinalHybrid"
      component={ObolFinalHybrid}
      durationInFrames={DURATION}
      fps={FPS}
      width={WIDTH}
      height={HEIGHT}
    />
  );
}

registerRoot(Root);

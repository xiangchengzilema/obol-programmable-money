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

const timeline = [
  {
    id: "01",
    start: 0,
    end: 8,
    label: "PROBLEM",
    text: "AI agents already read creator work, research posts, and paid knowledge sources. But most machine reads create no revenue for the people who produced the work.",
    accent: "AI reads do not pay",
  },
  {
    id: "02",
    start: 8,
    end: 15.5,
    label: "RESOLUTION",
    text: "Obol turns every useful agent read into a small USDC payment, a creator receipt, and an Arc transaction proof that judges can verify.",
    accent: "USDC + receipt + txHash",
  },
  {
    id: "03",
    start: 15.5,
    end: 23,
    label: "AGENT BUYER",
    text: "The buyer is not a human clicking subscribe. It is an autonomous research agent with a question, a budget, and a payment policy.",
    accent: "budgeted agent",
  },
  {
    id: "04",
    start: 23,
    end: 32.5,
    label: "SOURCE SELECTION",
    text: "Before any USDC moves, the agent evaluates sources, scores relevance, compares prices, checks cache reuse, and protects the remaining budget.",
    accent: "score / price / cache",
  },
  {
    id: "05",
    start: 32.5,
    end: 42,
    label: "LIVE SETTLEMENT",
    text: "Here, one source is selected. Circle submits the wallet payment, the creator receives USDC, and Arc returns the settlement proof.",
    accent: "Circle -> Arc proof",
  },
  {
    id: "06",
    start: 42,
    end: 50,
    label: "AUDIT LOG",
    text: "The decision log explains why the agent bought one source, skipped others, or reused a previous paid read.",
    accent: "explain every decision",
  },
  {
    id: "07",
    start: 50,
    end: 59,
    label: "MARKETPLACE",
    text: "In the marketplace, creators publish paid research with public previews. Full content stays locked until a valid payment is attached.",
    accent: "locked until paid",
  },
  {
    id: "08",
    start: 59,
    end: 68,
    label: "CREATOR SIDE",
    text: "Creator Studio shows the seller side: paid reads, revenue, receipt history, and an independent payout trail for each creator.",
    accent: "creator revenue",
  },
  {
    id: "09",
    start: 68,
    end: 79,
    label: "X402 ACCESS",
    text: "For external agents, Obol exposes the same market through an x402 style HTTP payment flow: request, receive a 402 challenge, attach payment proof, and unlock the resource.",
    accent: "402 challenge -> proof",
  },
  {
    id: "10",
    start: 79,
    end: 91,
    label: "TRACTION PROOF",
    text: "The traction ledger consolidates runs, receipts, payment status, and paid volume. Each agent receipt exposes the creator, amount, Circle transaction id, and Arc transaction hash.",
    accent: "verifiable receipt",
  },
  {
    id: "11",
    start: 91,
    end: 99,
    label: "CLOSING",
    text: "Obol makes machine reading accountable: agents choose sources, Circle settles USDC, Arc verifies the transfer, and creators get paid.",
    accent: "chain-verifiable payments",
  },
];

function currentSegment(frame) {
  const seconds = frame / FPS;
  return timeline.find((item) => seconds >= item.start && seconds < item.end) ?? timeline[timeline.length - 1];
}

function Keyword({ segment }) {
  const frame = useCurrentFrame();
  const local = frame - segment.start * FPS;
  const opacity = interpolate(local, [0, 12, (segment.end - segment.start) * FPS - 12, (segment.end - segment.start) * FPS], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const y = interpolate(local, [0, 16], [12, 0], { extrapolateRight: "clamp" });

  return (
    <div
      style={{
        position: "absolute",
        left: 48,
        top: 112,
        transform: `translateY(${y}px)`,
        opacity,
        display: "flex",
        alignItems: "center",
        gap: 14,
        padding: "12px 18px",
        borderRadius: 999,
        border: "1px solid rgba(100,255,218,.26)",
        background: "rgba(5, 18, 20, .62)",
        color: "#6ff2d2",
        fontFamily: "SFMono-Regular, Menlo, Consolas, monospace",
        fontSize: 18,
        fontWeight: 800,
        letterSpacing: 0,
        boxShadow: "0 24px 60px rgba(0,0,0,.28)",
      }}
    >
      <span style={{ color: "#f2ce63" }}>{segment.id}</span>
      <span>{segment.label}</span>
      <span style={{ color: "#b8c7c4", fontWeight: 700 }}>{segment.accent}</span>
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
  const y = interpolate(local, [0, 14], [20, 0], { extrapolateRight: "clamp" });

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        bottom: 0,
        minHeight: 128,
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        padding: "24px 92px",
        background: "linear-gradient(180deg, rgba(5,16,18,.70), rgba(5,16,18,.94))",
        borderTop: "1px solid rgba(100,255,218,.22)",
        opacity,
      }}
    >
      <div
        style={{
          transform: `translateY(${y}px)`,
          color: "#f7fbf8",
          fontFamily: "Inter, Arial, sans-serif",
          fontSize: 32,
          lineHeight: 1.22,
          fontWeight: 900,
          textAlign: "center",
          letterSpacing: 0,
          maxWidth: 1320,
          textShadow: "0 3px 16px rgba(0,0,0,.42)",
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
    <div
      style={{
        position: "absolute",
        left: 48,
        right: 48,
        bottom: 134,
        height: 4,
        borderRadius: 999,
        background: "rgba(255,255,255,.08)",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          width: `${Math.min(100, progress * 100)}%`,
          height: "100%",
          background: "linear-gradient(90deg, #5cefd0, #f2ce63)",
        }}
      />
    </div>
  );
}

function ObolDemo() {
  const frame = useCurrentFrame();
  const segment = currentSegment(frame);
  return (
    <AbsoluteFill style={{ backgroundColor: "#05090a" }}>
      <Video src={staticFile("obol_demo_v20_raw_plate.mp4")} />
      <Audio src={staticFile("obol_v22_indextts2_soft_voiceover.wav")} />
      <Keyword segment={segment} />
      <ProgressRail />
      <Subtitle segment={segment} />
    </AbsoluteFill>
  );
}

function Root() {
  return (
    <Composition
      id="ObolDemo"
      component={ObolDemo}
      durationInFrames={DURATION}
      fps={FPS}
      width={WIDTH}
      height={HEIGHT}
    />
  );
}

registerRoot(Root);

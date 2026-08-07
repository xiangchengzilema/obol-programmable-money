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
    label: "FRESH ARC EVIDENCE",
    text: "Obol binds a current-repository agent decision to a completed Circle transfer and verifies payer, token, recipient, amount, transaction hash, and block on Arc Testnet.",
    accent: "strict USDC proof",
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
    label: "SAFE JUDGE DEMO",
    text: "The anonymous playground is deliberately forced mock and labels its receipt as simulated. Paid content is released only for a confirmed live receipt or an explicit mock demo receipt.",
    accent: "mock is never called live",
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
    text: "Creator Studio separates confirmed live earnings from simulated demo volume, pending attempts, and failed transfers, with an independent receipt trail for each creator.",
    accent: "honest creator accounting",
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
    label: "THIS ITERATION",
    text: "Obol began before this hackathon. This iteration added programmable spend guards, strict Arc proof verification, concurrency-safe payment claims, honest settlement states, and forty-six passing backend tests.",
    accent: "existing project / substantial new work",
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
        border: "1px solid rgba(100,255,218,.30)",
        background: "linear-gradient(135deg, rgba(7, 20, 28, .72), rgba(11, 28, 40, .56))",
        color: "#69f4d6",
        fontFamily: "JetBrains Mono, SFMono-Regular, Menlo, Consolas, monospace",
        fontSize: 18,
        fontWeight: 900,
        letterSpacing: 0,
        boxShadow: "0 20px 60px rgba(0,0,0,.36)",
        backdropFilter: "blur(16px)",
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
        background: "linear-gradient(180deg, rgba(5, 13, 20, .62), rgba(5, 13, 20, .95))",
        borderTop: "1px solid rgba(100,255,218,.22)",
        opacity,
      }}
    >
      <div
        style={{
          transform: `translateY(${y}px)`,
          color: "#f7fbf8",
          fontFamily: "Inter, Arial, sans-serif",
          fontSize: 30,
          lineHeight: 1.22,
          fontWeight: 900,
          textAlign: "center",
          letterSpacing: 0,
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
    <div
      style={{
        position: "absolute",
        left: 48,
        right: 48,
        bottom: 138,
        height: 4,
        borderRadius: 999,
        background: "rgba(255,255,255,.10)",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          width: `${Math.min(100, progress * 100)}%`,
          height: "100%",
          background: "linear-gradient(90deg, #5cefd0, #56b1ff, #ff4fd8)",
        }}
      />
    </div>
  );
}

function ObolDemoV23() {
  const frame = useCurrentFrame();
  const segment = currentSegment(frame);
  return (
    <AbsoluteFill style={{ backgroundColor: "#05090a" }}>
      <Video src={staticFile("obol_demo_v23_raw_plate.mp4")} />
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
      id="ObolDemoV23"
      component={ObolDemoV23}
      durationInFrames={DURATION}
      fps={FPS}
      width={WIDTH}
      height={HEIGHT}
    />
  );
}

registerRoot(Root);


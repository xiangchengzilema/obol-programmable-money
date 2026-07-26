import { appendFileSync, existsSync, readFileSync } from "node:fs";
import { initiateDeveloperControlledWalletsClient } from "@circle-fin/developer-controlled-wallets";

const apiKey = process.env.CIRCLE_API_KEY;
const entitySecret = process.env.CIRCLE_ENTITY_SECRET;
const envPath = "../../backend/.env";

if (!apiKey) throw new Error("CIRCLE_API_KEY is required in backend/.env");
if (!entitySecret) throw new Error("CIRCLE_ENTITY_SECRET is required in backend/.env");

const client = initiateDeveloperControlledWalletsClient({ apiKey, entitySecret });

const walletSetResponse = await client.createWalletSet({
  name: "Obol Live Agent Wallet Set",
});

const walletSet = walletSetResponse.data?.walletSet;
if (!walletSet?.id) throw new Error("Wallet set creation failed: no ID returned");

const walletResponse = await client.createWallets({
  walletSetId: walletSet.id,
  blockchains: ["ARC-TESTNET"],
  count: 1,
  accountType: "EOA",
  metadata: [{ name: "Obol Agent Wallet", refId: "obol-agent" }],
});

const wallet = walletResponse.data?.wallets?.[0];
if (!wallet?.id) throw new Error("Wallet creation failed: no wallet returned");

const existingEnv = existsSync(envPath) ? readFileSync(envPath, "utf8") : "";
if (/^CIRCLE_AGENT_WALLET_ID=.+/m.test(existingEnv)) {
  console.log("CIRCLE_AGENT_WALLET_ID already exists in backend/.env; not appending.");
} else {
  appendFileSync(envPath, `\nCIRCLE_AGENT_WALLET_ID=${wallet.id}\n`);
}

console.log("Wallet set:", walletSet.id);
console.log("Agent wallet ID:", wallet.id);
console.log("Agent wallet address:", wallet.address);
console.log("Blockchain:", wallet.blockchain);

import { readFileSync } from "node:fs";
import { initiateDeveloperControlledWalletsClient } from "@circle-fin/developer-controlled-wallets";

const apiKey = process.env.CIRCLE_API_KEY;
const entitySecret = process.env.CIRCLE_ENTITY_SECRET;
if (!apiKey) throw new Error("CIRCLE_API_KEY is required in backend/.env");
if (!entitySecret) throw new Error("CIRCLE_ENTITY_SECRET is required in backend/.env");

const args = [
  ...process.argv.slice(2),
  ...(process.env.npm_config_addresses ? [`--addresses=${process.env.npm_config_addresses}`] : []),
  ...(process.env.npm_config_file ? [`--file=${process.env.npm_config_file}`] : []),
  ...(process.env.npm_config_blockchain ? [`--blockchain=${process.env.npm_config_blockchain}`] : []),
];
const addressesArg = args.find((a) => a.startsWith("--addresses="));
const fileArg = args.find((a) => a.startsWith("--file="));
const chainArg = args.find((a) => a.startsWith("--blockchain="));

const blockchain = (chainArg?.split("=")[1] || process.env.CIRCLE_FAUCET_BLOCKCHAIN || "ARC-TESTNET") as any;

let addresses: string[] = [];
if (addressesArg) {
  addresses = addressesArg.split("=")[1].split(",").map((a) => a.trim()).filter(Boolean);
}
if (fileArg) {
  const file = fileArg.split("=")[1];
  const raw = JSON.parse(readFileSync(file, "utf8"));
  addresses = raw.map((r: any) => r.address || r.payout_address).filter(Boolean);
}
if (!addresses.length) {
  throw new Error("Pass --addresses=0x...[,0x...] or --file=wallets.json");
}

const client = initiateDeveloperControlledWalletsClient({ apiKey, entitySecret });

for (const [i, address] of addresses.entries()) {
  try {
    const res = await client.requestTestnetTokens({
      address,
      blockchain,
      usdc: true,
    } as any);
    console.log(JSON.stringify({ index: i + 1, address, blockchain, status: res.status, ok: true }));
  } catch (err: any) {
    const status = err?.response?.status;
    const data = err?.response?.data;
    const message = err?.message || String(err);
    console.log(JSON.stringify({ index: i + 1, address, blockchain, status, ok: false, message, data }));
  }
}

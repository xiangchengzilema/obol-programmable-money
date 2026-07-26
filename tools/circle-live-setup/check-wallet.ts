import { initiateDeveloperControlledWalletsClient } from "@circle-fin/developer-controlled-wallets";

const apiKey = process.env.CIRCLE_API_KEY;
const entitySecret = process.env.CIRCLE_ENTITY_SECRET;
const walletId = process.env.CIRCLE_AGENT_WALLET_ID;

if (!apiKey) throw new Error("CIRCLE_API_KEY is required in backend/.env");
if (!entitySecret) throw new Error("CIRCLE_ENTITY_SECRET is required in backend/.env");
if (!walletId) throw new Error("CIRCLE_AGENT_WALLET_ID is required in backend/.env");

const client = initiateDeveloperControlledWalletsClient({ apiKey, entitySecret });

const wallet = await client.getWallet({ id: walletId });
console.log("Wallet:", wallet.data?.wallet);

const balance = await client.getWalletTokenBalance({ id: walletId });
console.log("Token balances:", JSON.stringify(balance.data, null, 2));

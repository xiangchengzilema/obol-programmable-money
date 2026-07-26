import { randomBytes } from "node:crypto";
import { appendFileSync, existsSync, mkdirSync, readFileSync } from "node:fs";
import { registerEntitySecretCiphertext } from "@circle-fin/developer-controlled-wallets";

const apiKey = process.env.CIRCLE_API_KEY;
const envPath = "../../backend/.env";

if (!apiKey) {
  throw new Error("CIRCLE_API_KEY is required in backend/.env");
}

const existingEnv = existsSync(envPath) ? readFileSync(envPath, "utf8") : "";
if (/^CIRCLE_ENTITY_SECRET=.+/m.test(existingEnv)) {
  throw new Error("CIRCLE_ENTITY_SECRET already exists in backend/.env; refusing to overwrite it.");
}

const entitySecret = randomBytes(32).toString("hex");
const recoveryDir = "./recovery";
mkdirSync(recoveryDir, { recursive: true });

await registerEntitySecretCiphertext({
  apiKey,
  entitySecret,
  recoveryFileDownloadPath: recoveryDir,
});

appendFileSync(envPath, `\n# Registered by tools/circle-live-setup\nCIRCLE_ENTITY_SECRET=${entitySecret}\n`);

console.log("Entity secret registered.");
console.log(`Recovery file saved in: ${recoveryDir}`);
console.log("CIRCLE_ENTITY_SECRET appended to backend/.env");

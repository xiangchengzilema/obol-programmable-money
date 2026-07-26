"""
Circle Wallet / Arc settlement layer for Obol.
Adapted from arc-micropayments. Real Circle API when CIRCLE_API_KEY is set,
otherwise a deterministic MOCK mode that returns fake but realistic tx hashes
so the full product runs (and the frontend/demo works) with zero config.

Each "an agent reads an article" = one nanopayment: agent wallet -> creator
payout address, in testnet USDC on Arc.
"""
import os
import json
import time
import base64
import hashlib
import urllib.request
import urllib.error
import uuid
import socket
import ssl

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ARC_BLOCKCHAIN = "ARC-TESTNET"
ARC_USDC_TOKEN_ID = os.getenv("ARC_USDC_TOKEN_ID", "15dc2b5d-0994-58b0-bf8c-3a0501148ee8")
ARC_USDC_TOKEN_ADDRESS = os.getenv("ARC_USDC_TOKEN_ADDRESS", "0x3600000000000000000000000000000000000000")
CIRCLE_API_BASE = "https://api.circle.com/v1/w3s"
TRANSFER_WAIT_SECONDS = float(os.getenv("OBOL_TRANSFER_WAIT_SECONDS", "18"))
TRANSFER_POLL_SECONDS = float(os.getenv("OBOL_TRANSFER_POLL_SECONDS", "1.2"))
TERMINAL_STATES = {"COMPLETE", "FAILED", "CANCELLED", "DENIED"}
RETRYABLE_HTTP = {408, 425, 429, 500, 502, 503, 504}
RETRY_ATTEMPTS = int(os.getenv("OBOL_CIRCLE_RETRY_ATTEMPTS", "3"))


class CircleService:
    def __init__(self, api_key=None, entity_secret=None):
        self.force_mock = os.getenv("OBOL_FORCE_MOCK", "").lower() in ("1", "true", "yes")
        self.api_key = "" if self.force_mock else (api_key or os.getenv("CIRCLE_API_KEY", ""))
        self.entity_secret = "" if self.force_mock else (entity_secret or os.getenv("CIRCLE_ENTITY_SECRET", ""))
        self.agent_wallet_id = "" if self.force_mock else os.getenv("CIRCLE_AGENT_WALLET_ID", "")
        self._public_key_pem = ""   # cached Circle entity public key (live mode only)

    @property
    def has_credentials(self):
        return bool(self.api_key and self.entity_secret)

    @property
    def is_configured(self):
        return bool(self.api_key and self.entity_secret and self.agent_wallet_id)

    @property
    def mode(self):
        return "live" if self.is_configured else "mock"

    def readiness(self):
        missing = []
        if self.force_mock:
            missing.append("OBOL_FORCE_MOCK enabled")
        if not self.api_key and not self.force_mock:
            missing.append("CIRCLE_API_KEY")
        if not self.entity_secret and not self.force_mock:
            missing.append("CIRCLE_ENTITY_SECRET")
        if not self.agent_wallet_id and not self.force_mock:
            missing.append("CIRCLE_AGENT_WALLET_ID")
        try:
            import cryptography  # noqa: F401
            crypto_ok = True
        except ImportError:
            crypto_ok = False
            if self.has_credentials:
                missing.append("cryptography package")
        return {
            "mode": self.mode,
            "force_mock": self.force_mock,
            "blockchain": ARC_BLOCKCHAIN,
            "token_id": ARC_USDC_TOKEN_ID,
            "token_address": ARC_USDC_TOKEN_ADDRESS,
            "ready_for_live_transfers": not missing,
            "missing": missing,
            "has_api_key": bool(self.api_key),
            "has_entity_secret": bool(self.entity_secret),
            "has_agent_wallet_id": bool(self.agent_wallet_id),
            "cryptography_installed": crypto_ok,
        }

    def _request(self, method, endpoint, data=None):
        url = f"{CIRCLE_API_BASE}/{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "ObolProgrammableMoney/1.0 (+https://github.com/xiangchengzilema/obol-programmable-money)",
        }
        body = json.dumps(data).encode("utf-8") if data else None
        last_error = None
        attempts = max(1, RETRY_ATTEMPTS)
        for attempt in range(1, attempts + 1):
            req = urllib.request.Request(url, data=body, headers=headers, method=method)
            try:
                resp = urllib.request.urlopen(req, timeout=30)
                return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                body_text = e.read().decode("utf-8", errors="replace")
                if e.code not in RETRYABLE_HTTP or attempt == attempts:
                    raise Exception(f"Circle API Error {e.code}: {body_text}")
                last_error = f"Circle API Error {e.code}: {body_text}"
            except (urllib.error.URLError, ssl.SSLError, socket.timeout, TimeoutError) as e:
                reason = getattr(e, "reason", e)
                if attempt == attempts:
                    raise Exception(f"Network Error after {attempts} attempts: {reason}")
                last_error = f"Network Error: {reason}"
            time.sleep(min(2 ** attempt, 8) * 0.35)
        raise Exception(last_error or "Circle request failed")

    def _entity_public_key(self):
        """Fetch (and cache) Circle's RSA public key for this entity."""
        if not self._public_key_pem:
            r = self._request("GET", "config/entity/publicKey")
            self._public_key_pem = r["data"]["publicKey"]
        return self._public_key_pem

    def _entity_secret_ciphertext(self):
        """Circle requires the 32-byte entity secret RSA-OAEP(SHA256)-encrypted with
        their public key, base64-encoded, fresh per request. `cryptography` is only
        imported here so mock mode stays dependency-free."""
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
        except ImportError as e:  # pragma: no cover - only hit in live mode
            raise RuntimeError(
                "Live Circle settlement needs the 'cryptography' package "
                "(pip install cryptography)."
            ) from e
        public_key = serialization.load_pem_public_key(self._entity_public_key().encode())
        ciphertext = public_key.encrypt(
            bytes.fromhex(self.entity_secret),
            padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),
                         algorithm=hashes.SHA256(), label=None),
        )
        return base64.b64encode(ciphertext).decode()

    def create_wallet(self, label="obol"):
        """Create an Arc wallet (mock returns a deterministic fake address)."""
        if not self.is_configured:
            addr = "0x" + hashlib.sha256(f"{label}{time.time()}".encode()).hexdigest()[:40]
            return {"id": f"mock_wallet_{int(time.time()*1000)}", "address": addr,
                    "blockchain": ARC_BLOCKCHAIN, "state": "LIVE"}
        ws = self._request("POST", "developer/walletSets", {
            "idempotencyKey": str(uuid.uuid4()),
            "name": f"Obol {label}",
            "entitySecretCiphertext": self._entity_secret_ciphertext(),
        })
        wsid = ws["data"]["walletSet"]["id"]
        r = self._request("POST", "developer/wallets", {
            "idempotencyKey": str(uuid.uuid4()),
            "walletSetId": wsid, "blockchains": [ARC_BLOCKCHAIN],
            "count": 1, "accountType": "EOA",
            "entitySecretCiphertext": self._entity_secret_ciphertext(),
            "metadata": [{"name": f"Obol {label}", "refId": f"obol-{label[:24]}"}],
        })
        w = r["data"]["wallets"][0]
        return {"id": w["id"], "address": w["address"],
                "blockchain": w["blockchain"], "state": w["state"]}

    def _wait_for_transaction(self, transaction_id, timeout_seconds=TRANSFER_WAIT_SECONDS):
        """Poll Circle until a transaction has a tx hash, reaches a terminal state,
        or the timeout expires."""
        if not transaction_id or timeout_seconds <= 0:
            return None
        deadline = time.time() + timeout_seconds
        last = None
        while time.time() < deadline:
            last = self.get_transaction(transaction_id)
            if last.get("txHash") or last.get("state") in TERMINAL_STATES:
                return last
            time.sleep(TRANSFER_POLL_SECONDS)
        return last

    def send_usdc_from_wallet(self, source_wallet_id, to_address, amount_usdc, reference=""):
        """
        Pay from a specific Circle wallet. Returns {tx_hash, state, amount, blockchain, mode}.
        Mock mode produces a realistic-looking 0x hash so receipts/the demo work.
        """
        amount = f"{float(amount_usdc):.6f}"
        if not self.is_configured:
            h = "0x" + hashlib.sha256(
                f"{source_wallet_id}{to_address}{amount}{reference}{time.time()}".encode()
            ).hexdigest()
            return {"tx_hash": h, "state": "COMPLETE", "amount": amount,
                    "blockchain": ARC_BLOCKCHAIN, "mode": "mock"}
        wallet_id = source_wallet_id or self.agent_wallet_id
        payload = {
            "idempotencyKey": str(uuid.uuid4()),
            "walletId": wallet_id,
            "blockchain": ARC_BLOCKCHAIN,
            "destinationAddress": to_address,
            "amounts": [amount],
            "feeLevel": "MEDIUM",
            "refId": reference[:32],
            "entitySecretCiphertext": self._entity_secret_ciphertext(),
        }
        if ARC_USDC_TOKEN_ADDRESS:
            payload["tokenAddress"] = ARC_USDC_TOKEN_ADDRESS
        else:
            payload["tokenId"] = ARC_USDC_TOKEN_ID
        r = self._request("POST", "developer/transactions/transfer", payload)
        tx = r["data"].get("transaction") or r["data"]
        final_tx = self._wait_for_transaction(tx.get("id"))
        if final_tx:
            tx = {**tx, **final_tx}
        return {"tx_hash": tx.get("txHash", ""), "state": tx.get("state", "INITIATED"),
                "transaction_id": tx.get("id", ""),
                "amount": amount, "blockchain": ARC_BLOCKCHAIN, "mode": "live"}

    def send_usdc(self, to_address, amount_usdc, reference=""):
        """
        Pay a creator from the configured agent wallet. Kept for the existing
        product flow; simulations can call send_usdc_from_wallet directly.
        """
        return self.send_usdc_from_wallet(self.agent_wallet_id, to_address, amount_usdc, reference)

    def get_transaction(self, transaction_id):
        """Fetch a Circle transaction by id."""
        if not transaction_id:
            raise ValueError("transaction_id is required")
        r = self._request("GET", f"transactions/{transaction_id}")
        return r["data"]["transaction"]

    def get_wallet_balance(self, wallet_id):
        """Fetch token balances for a Circle wallet."""
        if not wallet_id:
            raise ValueError("wallet_id is required")
        r = self._request("GET", f"wallets/{wallet_id}/balances")
        return r.get("data", r)

    @staticmethod
    def valid_address(addr):
        if not isinstance(addr, str) or not addr.startswith("0x") or len(addr) != 42:
            return False
        try:
            int(addr[2:], 16)
            return True
        except ValueError:
            return False

"""
Buyer wallet pool for live Obol payments.

The public demo has two kinds of wallets:
- creator payout wallets receive USDC
- buyer wallets represent independent readers/agents spending USDC

Manual marketplace unlocks and agent runs should spend from buyer wallets, not
from the single operator wallet, otherwise a funded buyer pool sits idle while
the main wallet gets drained.
"""
import json
import os
import random
import time
from pathlib import Path

from circle_service import ARC_USDC_TOKEN_ADDRESS, ARC_USDC_TOKEN_ID


BUYERS_FILE = Path(__file__).with_name("demo_buyer_wallets.json")
POOL_STATE_FILE = Path(__file__).with_name("buyer_wallet_pool_state.json")
BALANCE_CACHE_TTL = float(os.getenv("OBOL_BUYER_BALANCE_CACHE_SECONDS", "20"))


class WalletPoolExhausted(RuntimeError):
    """Raised when no configured payer wallet can cover a requested payment."""


def _load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def buyer_wallets():
    return _load_json(BUYERS_FILE, [])


def _buyer_number(buyer):
    try:
        return int(str(buyer.get("buyer_id", "")).split("-")[-1])
    except (TypeError, ValueError):
        return 0


def eligible_buyer_wallets():
    wallets = buyer_wallets()
    if not wallets:
        return []
    start = int(os.getenv("OBOL_BUYER_POOL_START", "1"))
    # User funded through buyer-030 first; avoid unfunded generated wallets by default.
    end = int(os.getenv("OBOL_BUYER_POOL_END", "30"))
    out = [
        w for w in wallets
        if w.get("wallet_id")
        and start <= _buyer_number(w) <= end
        and str(w.get("state", "")).upper() in {"LIVE", "DRY", ""}
    ]
    return sorted(out, key=_buyer_number)


def _ordered_wallets(wallets, buyer_hint=""):
    if not wallets:
        return []
    hinted = []
    if buyer_hint:
        hint = str(buyer_hint).lower()
        hinted = [
            w for w in wallets
            if hint in str(w.get("buyer_id", "")).lower()
            or hint in str(w.get("address", "")).lower()
        ]
    rest = [w for w in wallets if w not in hinted]
    state = _load_json(POOL_STATE_FILE, {})
    cursor = int(state.get("cursor", random.randrange(len(wallets)))) if wallets else 0
    cursor %= len(rest or wallets)
    rotated = (rest[cursor:] + rest[:cursor]) if rest else []
    return hinted + rotated


def _advance_cursor(selected_buyer_id, wallets):
    if not wallets:
        return
    numbers = [_buyer_number(w) for w in wallets]
    selected_number = _buyer_number({"buyer_id": selected_buyer_id})
    try:
        idx = numbers.index(selected_number)
    except ValueError:
        idx = random.randrange(len(wallets))
    _save_json(POOL_STATE_FILE, {
        "cursor": (idx + 1) % len(wallets),
        "last_buyer_id": selected_buyer_id,
        "updated_at": time.time(),
    })


def _is_usdc_token(token):
    if not isinstance(token, dict):
        return False
    symbol = str(token.get("symbol") or token.get("name") or "").upper()
    token_id = str(token.get("id") or token.get("tokenId") or "")
    token_address = str(
        token.get("tokenAddress")
        or token.get("address")
        or token.get("contractAddress")
        or ""
    ).lower()
    return (
        symbol == "USDC"
        or token_id == ARC_USDC_TOKEN_ID
        or (ARC_USDC_TOKEN_ADDRESS and token_address == ARC_USDC_TOKEN_ADDRESS.lower())
    )


def _float_amount(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_usdc_balance(data):
    """Parse Circle balance responses defensively across minor schema changes."""
    matches = []

    def walk(obj):
        if isinstance(obj, list):
            for item in obj:
                walk(item)
            return
        if not isinstance(obj, dict):
            return

        token = obj.get("token") if isinstance(obj.get("token"), dict) else obj
        if _is_usdc_token(token):
            for key in ("amount", "availableAmount", "available", "balance"):
                amount = _float_amount(obj.get(key))
                if amount is not None:
                    matches.append(amount)
                    break

        for value in obj.values():
            if isinstance(value, (dict, list)):
                walk(value)

    walk(data)
    return max(matches) if matches else 0.0


def _cached_balance(wallet_id):
    state = _load_json(POOL_STATE_FILE, {})
    cache = state.get("balances", {})
    item = cache.get(wallet_id)
    if not item:
        return None
    if time.time() - float(item.get("updated_at", 0)) > BALANCE_CACHE_TTL:
        return None
    return _float_amount(item.get("amount"))


def _store_balance(wallet_id, amount):
    state = _load_json(POOL_STATE_FILE, {})
    cache = state.setdefault("balances", {})
    cache[wallet_id] = {"amount": round(float(amount), 6), "updated_at": time.time()}
    _save_json(POOL_STATE_FILE, state)


def wallet_usdc_balance(circle, wallet_id):
    if not getattr(circle, "is_configured", False):
        return 1_000_000.0
    cached = _cached_balance(wallet_id)
    if cached is not None:
        return cached
    balance = _extract_usdc_balance(circle.get_wallet_balance(wallet_id))
    _store_balance(wallet_id, balance)
    return balance


def _is_insufficient_balance(exc):
    msg = str(exc).lower()
    return "insufficient token balance" in msg or "insufficient" in msg or "155258" in msg


def pay_from_buyer_pool(circle, to_address, amount_usdc, reference="", buyer_hint=""):
    """Send USDC from a funded buyer wallet when possible.

    Returns the normal CircleService transfer payload plus non-secret payer
    metadata: payer_buyer_id, payer_wallet_id, payer_address.
    """
    amount = float(amount_usdc)
    if amount <= 0:
        raise ValueError("amount_usdc must be greater than 0")

    if not getattr(circle, "is_configured", False):
        tx = circle.send_usdc_from_wallet("mock-buyer-wallet", to_address, amount, reference)
        tx.update({
            "payer_buyer_id": "mock-buyer",
            "payer_wallet_id": "mock-buyer-wallet",
            "payer_address": "",
        })
        return tx

    buyers = eligible_buyer_wallets()
    errors = []
    for buyer in _ordered_wallets(buyers, buyer_hint=buyer_hint):
        wallet_id = buyer.get("wallet_id")
        try:
            balance = wallet_usdc_balance(circle, wallet_id)
            if balance + 1e-9 < amount:
                errors.append(f"{buyer.get('buyer_id')} balance {balance:.6f} < {amount:.6f}")
                continue
            tx = circle.send_usdc_from_wallet(
                wallet_id,
                to_address,
                amount,
                reference=reference,
            )
            _store_balance(wallet_id, max(0.0, balance - amount))
            _advance_cursor(buyer.get("buyer_id", ""), buyers)
            tx.update({
                "payer_buyer_id": buyer.get("buyer_id", ""),
                "payer_wallet_id": wallet_id,
                "payer_address": buyer.get("address", ""),
            })
            return tx
        except Exception as exc:
            errors.append(f"{buyer.get('buyer_id')}: {str(exc)[:180]}")
            if not _is_insufficient_balance(exc):
                continue

    # Last resort: preserve old behavior if the operator wallet itself can cover it.
    agent_wallet_id = getattr(circle, "agent_wallet_id", "")
    if agent_wallet_id:
        try:
            balance = wallet_usdc_balance(circle, agent_wallet_id)
            if balance + 1e-9 >= amount:
                tx = circle.send_usdc_from_wallet(agent_wallet_id, to_address, amount, reference)
                _store_balance(agent_wallet_id, max(0.0, balance - amount))
                tx.update({
                    "payer_buyer_id": "operator-agent-wallet",
                    "payer_wallet_id": agent_wallet_id,
                    "payer_address": "",
                })
                return tx
            errors.append(f"operator wallet balance {balance:.6f} < {amount:.6f}")
        except Exception as exc:
            errors.append(f"operator wallet: {str(exc)[:180]}")

    checked = len(buyers) + (1 if agent_wallet_id else 0)
    raise WalletPoolExhausted(
        "No funded testnet buyer wallet can cover this source right now "
        f"({amount:.4f} USDC required, {checked} wallets checked). "
        "Fund more buyer wallets or choose a lower-priced article."
    )

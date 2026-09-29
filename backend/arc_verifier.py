"""Server-side Arc Testnet transaction verification.

The browser never talks to an Arc RPC directly.  This module queries the RPC
from the backend, validates that the endpoint is serving Arc Testnet, and
returns a deliberately small set of transaction, receipt, and block fields.
RPC URLs may contain provider credentials, so callers only ever receive the
endpoint hostname.
"""

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlsplit


ARC_CHAIN_ID = 5_042_002
ARC_USDC_ADDRESS = "0x3600000000000000000000000000000000000000"
ERC20_TRANSFER_TOPIC = (
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
)
USDC_DECIMALS = 6
PRIMARY_RPC_URL = "https://rpc.testnet.arc.network"
FALLBACK_RPC_URL = "https://rpc.testnet.arc.io"
EXPLORER_API_URL = "https://explorer.testnet.arc.io/api/v2"
TX_HASH_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
HEX_RE = re.compile(r"^0x[0-9a-fA-F]+$")
ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
PUBLIC_RPC_HOSTS = {"rpc.testnet.arc.network", "rpc.testnet.arc.io"}
VERIFY_CACHE_TTL_SECONDS = max(
    30, int(os.getenv("OBOL_ARC_VERIFY_CACHE_SECONDS", "600"))
)
_VERIFY_CACHE = {}
_VERIFY_LOCK = threading.Lock()


class ArcVerifierError(Exception):
    """Base class for safe verifier failures."""


class InvalidTransactionHash(ArcVerifierError):
    """Raised before any network request when a hash is malformed."""


class TransactionNotFound(ArcVerifierError):
    """Raised when all reachable Arc RPCs agree the transaction is absent."""


class ArcRPCError(ArcVerifierError):
    """Raised when Arc RPC verification is unavailable or inconsistent."""


def _rpc_hostname(url):
    """Return a safe endpoint label without leaking provider credentials."""
    try:
        hostname = (urlsplit(url).hostname or "unknown").lower()
    except (TypeError, ValueError):
        return "unknown"
    return hostname if hostname in PUBLIC_RPC_HOSTS else "configured-rpc"


def _valid_rpc_url(url):
    if not isinstance(url, str) or any(ch in url for ch in "\r\n\t"):
        return False
    try:
        parsed = urlsplit(url)
    except (TypeError, ValueError):
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname)


def rpc_urls():
    """Return ordered RPC candidates, with an optional server-side override.

    Without an override the official ``.network`` host is preferred,
    with the public ``.io`` host as fallback.  ``ARC_RPC_URL`` replaces the
    preferred endpoint while retaining the public ``.io`` fallback.
    """
    override = (os.getenv("ARC_RPC_URL") or "").strip()
    candidates = [override or PRIMARY_RPC_URL, FALLBACK_RPC_URL]
    urls = []
    for url in candidates:
        if not _valid_rpc_url(url) or url in urls:
            continue
        urls.append(url)
    return urls or [FALLBACK_RPC_URL]


def rpc_hosts():
    """Safe endpoint identifiers suitable for an API response."""
    return [_rpc_hostname(url) for url in rpc_urls()]


def _rpc_call(rpc_url, method, params, timeout=8):
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }).encode("utf-8")
    try:
        request = urllib.request.Request(
            rpc_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "ObolArcVerifier/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            # JSON-RPC responses here are small.  Bound the read so a bad
            # upstream cannot make the public API consume unbounded memory.
            raw = response.read(2_000_001)
    except urllib.error.HTTPError as exc:
        raise ArcRPCError(f"RPC HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise ArcRPCError("RPC request failed") from None
    if len(raw) > 2_000_000:
        raise ArcRPCError("RPC response too large")
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        raise ArcRPCError("RPC returned invalid JSON") from None
    if not isinstance(body, dict) or "error" in body or "result" not in body:
        raise ArcRPCError("RPC returned an error")
    return body["result"]


def _explorer_json(path, timeout=8):
    """Read the public Arc Testnet explorer only after both RPCs miss a tx.

    The path is assembled solely from a validated hash or numeric block height.
    An explorer failure is an unavailable check, never proof of a missing tx.
    """
    request = urllib.request.Request(
        EXPLORER_API_URL + path,
        headers={"Accept": "application/json", "User-Agent": "ObolArcVerifier/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(2_000_001)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise TransactionNotFound("transaction not found by Arc explorer") from None
        raise ArcRPCError("Arc explorer request failed") from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise ArcRPCError("Arc explorer request failed") from None
    if len(raw) > 2_000_000:
        raise ArcRPCError("Arc explorer response too large")
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        raise ArcRPCError("Arc explorer returned invalid JSON") from None
    if not isinstance(body, dict):
        raise ArcRPCError("Arc explorer returned invalid data")
    return body


def _decimal_int(value, field):
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]+", str(value)):
        raise ArcRPCError(f"Arc explorer returned invalid {field}")
    return int(value)


def _explorer_address(value, field):
    if not isinstance(value, dict):
        raise ArcRPCError(f"Arc explorer returned invalid {field}")
    return _safe_address(value.get("hash"), field)


def _hex_int(value, field, allow_none=False):
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or not HEX_RE.fullmatch(value):
        raise ArcRPCError(f"RPC returned invalid {field}")
    try:
        return int(value, 16)
    except ValueError:
        raise ArcRPCError(f"RPC returned invalid {field}") from None


def _safe_hash(value, field, allow_none=False):
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or not TX_HASH_RE.fullmatch(value):
        raise ArcRPCError(f"RPC returned invalid {field}")
    return value.lower()


def _safe_address(value, field, allow_none=False):
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or not ADDRESS_RE.fullmatch(value):
        raise ArcRPCError(f"RPC returned invalid {field}")
    return value.lower()


def _topic_address(value, field):
    if not isinstance(value, str) or not TX_HASH_RE.fullmatch(value):
        raise ArcRPCError(f"RPC returned invalid {field}")
    return _safe_address("0x" + value[-40:], field)


def _usdc_transfers(receipt):
    """Return only sanitized USDC Transfer events, not arbitrary raw logs."""
    if receipt is None:
        return []
    logs = receipt.get("logs", [])
    if not isinstance(logs, list):
        raise ArcRPCError("RPC returned invalid receipt logs")
    transfers = []
    for log in logs:
        if not isinstance(log, dict):
            raise ArcRPCError("RPC returned invalid receipt log")
        address = log.get("address")
        if not isinstance(address, str) or address.lower() != ARC_USDC_ADDRESS:
            continue
        topics = log.get("topics")
        if not isinstance(topics, list) or not topics:
            raise ArcRPCError("RPC returned invalid USDC log topics")
        if str(topics[0]).lower() != ERC20_TRANSFER_TOPIC:
            continue
        if len(topics) < 3:
            raise ArcRPCError("RPC returned incomplete USDC transfer")
        amount = _hex_int(log.get("data"), "USDC transfer amount")
        transfers.append({
            "token_contract": ARC_USDC_ADDRESS,
            "from": _topic_address(topics[1], "USDC sender"),
            "to": _topic_address(topics[2], "USDC recipient"),
            "amount_base_units": amount,
            "amount_usdc": f"{amount / (10 ** USDC_DECIMALS):.6f}",
        })
    return transfers


def _verify_with_rpc(tx_hash, rpc_url):
    chain_id = _hex_int(_rpc_call(rpc_url, "eth_chainId", []), "chain id")
    if chain_id != ARC_CHAIN_ID:
        raise ArcRPCError("RPC is not serving Arc Testnet")

    receipt = _rpc_call(rpc_url, "eth_getTransactionReceipt", [tx_hash])
    transaction = _rpc_call(rpc_url, "eth_getTransactionByHash", [tx_hash])
    if receipt is None and transaction is None:
        raise TransactionNotFound("transaction not found")
    if transaction is None or not isinstance(transaction, dict):
        raise ArcRPCError("RPC returned an incomplete transaction")
    if receipt is not None and not isinstance(receipt, dict):
        raise ArcRPCError("RPC returned an invalid receipt")

    returned_hash = _safe_hash(transaction.get("hash"), "transaction hash")
    if returned_hash != tx_hash.lower():
        raise ArcRPCError("RPC returned a mismatched transaction")

    transaction_block_number_hex = transaction.get("blockNumber")
    transaction_block_hash = _safe_hash(
        transaction.get("blockHash"), "transaction block hash", allow_none=True
    )
    transaction_index_hex = transaction.get("transactionIndex")

    if receipt is not None:
        receipt_tx_hash = _safe_hash(
            receipt.get("transactionHash"), "receipt transaction hash"
        )
        if receipt_tx_hash != returned_hash:
            raise ArcRPCError("RPC returned a receipt for a different transaction")
        receipt_block_number_hex = receipt.get("blockNumber")
        receipt_block_hash = _safe_hash(
            receipt.get("blockHash"), "receipt block hash"
        )
        receipt_transaction_index_hex = receipt.get("transactionIndex")
        if transaction_block_number_hex != receipt_block_number_hex:
            raise ArcRPCError("RPC returned inconsistent transaction block numbers")
        if transaction_block_hash != receipt_block_hash:
            raise ArcRPCError("RPC returned inconsistent transaction block hashes")
        if transaction_index_hex != receipt_transaction_index_hex:
            raise ArcRPCError("RPC returned inconsistent transaction indexes")
    else:
        receipt_tx_hash = None
        receipt_block_number_hex = None
        receipt_block_hash = None
        receipt_transaction_index_hex = None

    block_number_hex = (
        receipt_block_number_hex if receipt else transaction_block_number_hex
    )
    block_number = _hex_int(block_number_hex, "block number", allow_none=True)
    block = None
    timestamp = None
    timestamp_iso = None
    if block_number_hex is not None:
        block = _rpc_call(rpc_url, "eth_getBlockByNumber", [block_number_hex, False])
        if not isinstance(block, dict):
            raise ArcRPCError("RPC returned an incomplete block")
        returned_block_number = _hex_int(block.get("number"), "returned block number")
        returned_block_hash = _safe_hash(block.get("hash"), "returned block hash")
        if returned_block_number != block_number:
            raise ArcRPCError("RPC returned a different block number")
        expected_block_hash = receipt_block_hash or transaction_block_hash
        if expected_block_hash and returned_block_hash != expected_block_hash:
            raise ArcRPCError("RPC returned a different block hash")
        timestamp = _hex_int(block.get("timestamp"), "block timestamp")
        try:
            timestamp_iso = datetime.fromtimestamp(
                timestamp, timezone.utc
            ).isoformat().replace("+00:00", "Z")
        except (OverflowError, OSError, ValueError):
            raise ArcRPCError("RPC returned invalid block timestamp") from None

    receipt_status = _hex_int(
        receipt.get("status") if receipt else None,
        "receipt status",
        allow_none=True,
    )
    if receipt_status not in {None, 0, 1}:
        raise ArcRPCError("RPC returned invalid receipt status")
    successful = None if receipt_status is None else receipt_status == 1
    if receipt is None:
        status = "pending"
    else:
        status = "success" if successful else "reverted"

    input_data = transaction.get("input") or "0x"
    if not isinstance(input_data, str) or not re.fullmatch(r"0x(?:[0-9a-fA-F]{2})*", input_data):
        raise ArcRPCError("RPC returned invalid transaction input")

    transaction_index = (
        receipt_transaction_index_hex if receipt else transaction_index_hex
    )
    gas_used = receipt.get("gasUsed") if receipt else None
    cumulative_gas_used = receipt.get("cumulativeGasUsed") if receipt else None
    effective_gas_price = receipt.get("effectiveGasPrice") if receipt else None

    return {
        "network": "arc-testnet",
        "chain_id": chain_id,
        "rpc_host": _rpc_hostname(rpc_url),
        "found": True,
        "confirmed": receipt is not None and block_number is not None,
        "verified": bool(receipt is not None and block_number is not None and successful),
        "status": status,
        "successful": successful,
        "transaction": {
            "hash": returned_hash,
            "from": _safe_address(transaction.get("from"), "sender"),
            "to": _safe_address(transaction.get("to"), "recipient", allow_none=True),
            "block_number": _hex_int(
                transaction_block_number_hex,
                "transaction block number",
                allow_none=True,
            ),
            "block_hash": transaction_block_hash,
            "value_wei": str(_hex_int(transaction.get("value"), "transaction value")),
            "nonce": _hex_int(transaction.get("nonce"), "transaction nonce"),
            "input_bytes": (len(input_data) - 2) // 2,
        },
        "receipt": {
            "transaction_hash": receipt_tx_hash,
            "block_number": block_number,
            "block_hash": receipt_block_hash or transaction_block_hash,
            "transaction_index": _hex_int(
                transaction_index, "transaction index", allow_none=True
            ),
            "gas_used": _hex_int(gas_used, "gas used", allow_none=True),
            "cumulative_gas_used": _hex_int(
                cumulative_gas_used, "cumulative gas used", allow_none=True
            ),
            "effective_gas_price_wei": (
                str(_hex_int(effective_gas_price, "effective gas price"))
                if effective_gas_price is not None else None
            ),
            "contract_address": _safe_address(
                receipt.get("contractAddress") if receipt else None,
                "contract address",
                allow_none=True,
            ),
            "usdc_transfers": _usdc_transfers(receipt),
        },
        "block": {
            "number": block_number,
            "hash": (
                _safe_hash(block.get("hash"), "block hash") if block else None
            ),
            "timestamp": timestamp,
            "timestamp_iso": timestamp_iso,
        },
    }


def _verify_with_explorer(tx_hash):
    """Cross-check an old receipt with Arc's public explorer if RPC history misses it.

    This is a separately labelled indexer result, not misrepresented as an RPC
    response. Every field used to bind the committed evidence is validated.
    """
    tx = _explorer_json(f"/transactions/{tx_hash}")
    if _safe_hash(tx.get("hash"), "explorer transaction hash") != tx_hash:
        raise ArcRPCError("Arc explorer returned a different transaction")
    if tx.get("status") != "ok" or tx.get("is_pending_update"):
        raise ArcRPCError("Arc explorer transaction is not confirmed successful")

    block_number = _decimal_int(tx.get("block_number"), "block number")
    if block_number <= 0:
        raise ArcRPCError("Arc explorer returned invalid block number")
    try:
        block = _explorer_json(f"/blocks/{block_number}")
    except TransactionNotFound:
        raise ArcRPCError("Arc explorer returned an incomplete block") from None
    if _decimal_int(block.get("height"), "block height") != block_number:
        raise ArcRPCError("Arc explorer returned a different block")
    block_hash = _safe_hash(block.get("hash"), "block hash")
    try:
        block_time = block.get("timestamp")
        if not isinstance(block_time, str) or not block_time.endswith("Z"):
            raise ValueError("not a UTC timestamp")
        timestamp = int(datetime.fromisoformat(
            block_time.replace("Z", "+00:00")
        ).timestamp())
    except (TypeError, ValueError, OverflowError):
        raise ArcRPCError("Arc explorer returned invalid block timestamp") from None

    raw_input = tx.get("raw_input")
    if not isinstance(raw_input, str) or not re.fullmatch(
        r"0x(?:[0-9a-fA-F]{2})*", raw_input
    ):
        raise ArcRPCError("Arc explorer returned invalid transaction input")
    if tx.get("token_transfers_overflow"):
        raise ArcRPCError("Arc explorer transfer list is incomplete")
    transfers = tx.get("token_transfers")
    if not isinstance(transfers, list):
        raise ArcRPCError("Arc explorer returned invalid transfers")
    usdc_transfers = []
    for transfer in transfers:
        if not isinstance(transfer, dict) or not isinstance(transfer.get("token"), dict):
            raise ArcRPCError("Arc explorer returned invalid transfer")
        if str(transfer["token"].get("address_hash", "")).lower() != ARC_USDC_ADDRESS:
            continue
        if _safe_hash(transfer.get("transaction_hash"), "transfer transaction hash") != tx_hash:
            raise ArcRPCError("Arc explorer returned a transfer for another transaction")
        if _decimal_int(transfer.get("block_number"), "transfer block number") != block_number:
            raise ArcRPCError("Arc explorer returned a transfer from another block")
        if _safe_hash(transfer.get("block_hash"), "transfer block hash") != block_hash:
            raise ArcRPCError("Arc explorer returned an inconsistent transfer block")
        total = transfer.get("total")
        if not isinstance(total, dict) or _decimal_int(total.get("decimals"), "USDC decimals") != USDC_DECIMALS:
            raise ArcRPCError("Arc explorer returned invalid USDC decimals")
        amount = _decimal_int(total.get("value"), "USDC amount")
        usdc_transfers.append({
            "token_contract": ARC_USDC_ADDRESS,
            "from": _explorer_address(transfer.get("from"), "USDC sender"),
            "to": _explorer_address(transfer.get("to"), "USDC recipient"),
            "amount_base_units": amount,
            "amount_usdc": f"{amount / (10 ** USDC_DECIMALS):.6f}",
        })

    sender = _explorer_address(tx.get("from"), "sender")
    recipient = _explorer_address(tx.get("to"), "recipient")
    return {
        "network": "arc-testnet",
        "chain_id": ARC_CHAIN_ID,
        "rpc_host": "explorer.testnet.arc.io",
        "source_type": "public-explorer-fallback",
        "found": True,
        "confirmed": True,
        "verified": True,
        "status": "success",
        "successful": True,
        "transaction": {
            "hash": tx_hash,
            "from": sender,
            "to": recipient,
            "block_number": block_number,
            "block_hash": block_hash,
            "value_wei": str(_decimal_int(tx.get("value"), "transaction value")),
            "nonce": _decimal_int(tx.get("nonce"), "transaction nonce"),
            "input_bytes": (len(raw_input) - 2) // 2,
        },
        "receipt": {
            "transaction_hash": tx_hash,
            "block_number": block_number,
            "block_hash": block_hash,
            "transaction_index": _decimal_int(tx.get("position"), "transaction index"),
            "gas_used": _decimal_int(tx.get("gas_used"), "gas used"),
            "cumulative_gas_used": None,
            "effective_gas_price_wei": str(_decimal_int(tx.get("gas_price"), "gas price")),
            "contract_address": None,
            "usdc_transfers": usdc_transfers,
        },
        "block": {
            "number": block_number,
            "hash": block_hash,
            "timestamp": timestamp,
            "timestamp_iso": datetime.fromtimestamp(
                timestamp, timezone.utc
            ).isoformat().replace("+00:00", "Z"),
        },
    }


def verify_transaction(tx_hash):
    """Verify one transaction against Arc Testnet with endpoint fallback."""
    if not isinstance(tx_hash, str) or not TX_HASH_RE.fullmatch(tx_hash):
        raise InvalidTransactionHash("tx_hash must be 0x followed by 64 hex characters")

    normalized_hash = tx_hash.lower()
    now = time.monotonic()
    cached = _VERIFY_CACHE.get(normalized_hash)
    if cached and now - cached[0] < VERIFY_CACHE_TTL_SECONDS:
        return cached[1]

    # Single-flight verification keeps a burst of public requests from tying up
    # every Gunicorn thread with duplicate upstream RPC calls.
    if not _VERIFY_LOCK.acquire(blocking=False):
        raise ArcRPCError("Arc evidence verification is already in progress")
    try:
        now = time.monotonic()
        cached = _VERIFY_CACHE.get(normalized_hash)
        if cached and now - cached[0] < VERIFY_CACHE_TTL_SECONDS:
            return cached[1]

        not_found = 0
        rpc_errors = 0
        urls = rpc_urls()
        for rpc_url in urls:
            try:
                result = _verify_with_rpc(normalized_hash, rpc_url)
                if result.get("verified"):
                    _VERIFY_CACHE.clear()
                    _VERIFY_CACHE[normalized_hash] = (time.monotonic(), result)
                return result
            except TransactionNotFound:
                not_found += 1
            except ArcRPCError:
                rpc_errors += 1

        if not_found == len(urls):
            # Public RPC nodes can lack historical data even though the
            # transaction is indexed on Arc Testnet. Do not report a false
            # 404 until the public explorer has also been checked.
            result = _verify_with_explorer(normalized_hash)
            if result.get("verified"):
                _VERIFY_CACHE.clear()
                _VERIFY_CACHE[normalized_hash] = (time.monotonic(), result)
            return result
        if rpc_errors or not_found:
            raise ArcRPCError("Arc RPC verification unavailable")
        raise ArcRPCError("Arc RPC verification unavailable")
    finally:
        _VERIFY_LOCK.release()


def verify_evidence_bundle(evidence):
    """Strictly bind a successful Arc receipt to the committed Obol evidence."""
    try:
        evidence_id = str(evidence["evidence_id"])
        circle = evidence["circle"]
        arc = evidence["arc"]
        tx_hash = str(arc["transaction_hash"]).lower()
        payer = str(arc["payer_address"]).lower()
        creator = str(arc["creator_address"]).lower()
        token = str(arc["token_contract"]).lower()
        amount = int(arc["amount_base_units"])
        block_number = int(arc["block_number"])
        block_hash = str(arc["block_hash"]).lower()
        chain_id = int(arc["chain_id"])
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ArcRPCError("evidence bundle is invalid") from None

    proof = verify_transaction(tx_hash)
    transfers = proof.get("receipt", {}).get("usdc_transfers", [])
    matching_transfer = next((item for item in transfers if (
        item.get("token_contract") == token
        and item.get("from") == payer
        and item.get("to") == creator
        and item.get("amount_base_units") == amount
    )), None)
    matches = (
        circle.get("state") == "COMPLETE"
        and proof.get("verified") is True
        and proof.get("successful") is True
        and proof.get("chain_id") == chain_id == ARC_CHAIN_ID
        and proof.get("transaction", {}).get("hash") == tx_hash
        and proof.get("transaction", {}).get("from") == payer
        and proof.get("transaction", {}).get("to") == token
        and proof.get("transaction", {}).get("block_number") == block_number
        and proof.get("transaction", {}).get("block_hash") == block_hash
        and proof.get("receipt", {}).get("transaction_hash") == tx_hash
        and proof.get("receipt", {}).get("block_number") == block_number
        and proof.get("receipt", {}).get("block_hash") == block_hash
        and proof.get("block", {}).get("number") == block_number
        and proof.get("block", {}).get("hash") == block_hash
        and matching_transfer is not None
    )
    if not matches:
        raise ArcRPCError("on-chain receipt does not match committed evidence")

    return {
        **proof,
        "evidence_id": evidence_id,
        "evidence_match": True,
        "matched_transfer": matching_transfer,
    }

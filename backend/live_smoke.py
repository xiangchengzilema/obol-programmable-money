"""
Minimal live Circle/Arc transfer smoke test.

This sends a tiny Arc Testnet USDC transfer through the same CircleService path
used by Obol's agent payments. Run only after funding the agent wallet from the
Circle Faucet.

Usage:
  cd backend
  python live_smoke.py --confirm-live-transfer --to 0x... --amount 0.001
"""
import argparse
import json
import time

from circle_service import CircleService


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-live-transfer", action="store_true")
    parser.add_argument("--to", required=True, help="Destination 0x address on Arc Testnet")
    parser.add_argument("--amount", default="0.001", help="USDC amount, default 0.001")
    args = parser.parse_args()

    if not args.confirm_live_transfer:
        raise SystemExit("Refusing to send. Add --confirm-live-transfer after funding the wallet.")
    if not CircleService.valid_address(args.to):
        raise SystemExit("Invalid destination address.")

    circle = CircleService()
    status = circle.readiness()
    if status["mode"] != "live" or not status["ready_for_live_transfers"]:
        raise SystemExit("Circle live settlement is not ready:\n" + json.dumps(status, indent=2))

    result = circle.send_usdc(args.to, args.amount, reference="obol-live-smoke")
    transaction_id = result.get("transaction_id")
    print(json.dumps(result, indent=2))

    if transaction_id:
        terminal = {"COMPLETE", "FAILED", "CANCELLED", "DENIED"}
        for _ in range(20):
            tx = circle.get_transaction(transaction_id)
            print(json.dumps({
                "transaction_id": tx.get("id"),
                "state": tx.get("state"),
                "tx_hash": tx.get("txHash", ""),
                "blockchain": tx.get("blockchain"),
            }, indent=2))
            if tx.get("state") in terminal:
                break
            time.sleep(3)


if __name__ == "__main__":
    main()

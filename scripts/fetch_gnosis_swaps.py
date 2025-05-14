#!/usr/bin/env python3
"""
Fetch and decode all Swap logs from a Uniswap-V3-style pool on Gnosis Chain.

Example
-------
$ GNOSIS_RPC=https://rpc.gnosischain.com \
  python fetch_gnosis_swaps.py \
      --pool 0xac12a0c39266e0214cdbcee98c53cc13e5722b8a \
      --from-block 40_000_000
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Dict, Iterable, Any

from eth_utils import event_abi_to_log_topic, to_checksum_address
from web3 import Web3
from web3.exceptions import LogTopicError
from web3.types import LogReceipt

# ---------------------------------------------------------------------------
# Event ABI
# ---------------------------------------------------------------------------
SWAP_EVENT_ABI = {
    "anonymous": False,
    "name": "Swap",
    "type": "event",
    "inputs": [
        {"indexed": True, "internalType": "address", "name": "sender", "type": "address"},
        {"indexed": True, "internalType": "address", "name": "recipient", "type": "address"},
        {"indexed": False, "internalType": "int256", "name": "amount0", "type": "int256"},
        {"indexed": False, "internalType": "int256", "name": "amount1", "type": "int256"},
        {"indexed": False, "internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
        {"indexed": False, "internalType": "uint128", "name": "liquidity", "type": "uint128"},
        {"indexed": False, "internalType": "int24", "name": "tick", "type": "int24"},
    ],
}

# Pre-compute topic0 for the Swap event once at import time
SWAP_TOPIC0 = event_abi_to_log_topic(SWAP_EVENT_ABI)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def decode_swap_log(w3: Web3, log: LogReceipt) -> Dict[str, Any]:
    """Decode a single Swap log into primitive Python types."""
    # Indexed address parameters are stored in topics[1] and topics[2]
    sender = to_checksum_address(log["topics"][1][-20:].hex())
    recipient = to_checksum_address(log["topics"][2][-20:].hex())

    # Non-indexed parameters come from the ABI-encoded data blob
    data_types = [inp["type"] for inp in SWAP_EVENT_ABI["inputs"] if not inp["indexed"]]
    # web3.py >= 6 removes `decode_abi`; use the ABICodec `.decode` method instead.
    # `log["data"]` is a HexBytes instance; `bytes()` converts it directly.
    raw_bytes = bytes(log["data"])  # Already binary
    amount0, amount1, sqrt_price_x96, liquidity, tick = w3.codec.decode(data_types, raw_bytes)

    return {
        "blockNumber": log["blockNumber"],
        "txHash": log["transactionHash"].hex(),
        "logIndex": log["logIndex"],
        "sender": sender,
        "recipient": recipient,
        "amount0": int(amount0),
        "amount1": int(amount1),
        "sqrtPriceX96": int(sqrt_price_x96),
        "liquidity": int(liquidity),
        "tick": int(tick),
    }


def iter_swap_logs(
    w3: Web3,
    pool: str,
    from_block: int,
    to_block: int | str = "latest",
    chunk: int = 2_000,
) -> Iterable[LogReceipt]:
    """Yield Swap logs in provider-friendly block chunks (≤10k blocks typical)."""
    pool = to_checksum_address(pool)
    start = from_block

    while True:
        end: int | str
        if isinstance(to_block, int):
            end = min(start + chunk - 1, to_block)
        else:
            end = start + chunk - 1

        logs = w3.eth.get_logs(
            {
                "address": pool,
                "fromBlock": start,
                "toBlock": end,
                "topics": [SWAP_TOPIC0],
            }
        )
        for lg in logs:
            yield lg

        # Break conditions
        if isinstance(to_block, int) and end >= to_block:
            break
        if isinstance(to_block, str) and to_block == "latest":
            # If tracking latest, keep sliding window forward indefinitely.
            start = end + 1
            continue

        # Slide the window forward
        start = end + 1


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Uniswap-V3 Swap logs on Gnosis Chain")
    parser.add_argument(
        "--rpc",
        default=os.getenv("GNOSIS_RPC", "https://rpc.gnosischain.com"),
        help="Gnosis JSON-RPC endpoint",
    )
    parser.add_argument("--pool", required=True, help="Pool (contract) address that emits Swap")
    parser.add_argument("--from-block", type=int, required=True, help="Start block (inclusive)")
    parser.add_argument("--to-block", type=str, default="latest", help="End block or 'latest'")
    parser.add_argument(
        "--chunk", type=int, default=2_000, help="Block span per eth_getLogs query"
    )
    args = parser.parse_args()

    w3 = Web3(Web3.HTTPProvider(args.rpc, request_kwargs={"timeout": 60}))
    if not w3.is_connected():
        raise SystemExit(f"Cannot connect to {args.rpc}")

    # Convert to_block to int when numeric for cheap comparisons
    to_block: int | str = int(args.to_block) if args.to_block.isnumeric() else args.to_block

    try:
        for raw in iter_swap_logs(w3, args.pool, args.from_block, to_block, args.chunk):
            decoded = decode_swap_log(w3, raw)
            # Output ND-JSON for easy downstream consumption
            print(json.dumps(decoded, separators=(",", ":"), sort_keys=True))
    except LogTopicError:
        raise SystemExit("The target contract does not emit a Uniswap-V3-style Swap event.")
    except KeyboardInterrupt:
        # Allow graceful Ctrl-C termination without stacktrace
        pass


if __name__ == "__main__":
    main()

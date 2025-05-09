"""Helper for simulating Balancer BatchRouter.swapExactIn (sell GNO → sDAI) via Tenderly.

Assumes the sender wallet already approved the required amount of GNO to the BatchRouter.
Only builds and simulates the swap transaction – **does not** broadcast it on-chain.

The helper exposes two public functions:

    • build_sell_gno_to_sdai_swap_tx(w3, client, amount_in_wei, min_amount_out_wei, sender)
        ↳ Returns a Tenderly-compatible transaction dict ready for simulation.

    • sell_gno_to_sdai(w3, client, amount_in_wei, min_amount_out_wei, sender)
        ↳ Convenience wrapper that builds the tx → triggers Tenderly simulation →
          pretty-prints & returns the simulation result.

Usage example::

    from decimal import Decimal
    import os
    from web3 import Web3
    from tenderly_api import TenderlyClient  # adjust import to your project layout
    from balancer_swap import sell_gno_to_sdai

    w3 = Web3(Web3.HTTPProvider(os.environ["GNOSIS_RPC_URL"]))
    client = TenderlyClient(w3)
    sender = os.environ["WALLET_ADDRESS"]

    # sell 0.1 GNO and require at least 1 sDAI out
    amt_in = w3.to_wei(Decimal("0.1"), "ether")
    min_out = w3.to_wei(Decimal("1"), "ether")

    sell_gno_to_sdai(w3, client, amt_in, min_out, sender)

The path hard-coded below is the canonical 2-hop GNO→WSTETH buffer→sDAI pool on
Gnosis at the time of writing (May 2025). Update the constants if Balancer
migrates liquidity.
"""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Any, Dict, List, Optional

from eth_typing import ChecksumAddress
from web3 import Web3

from .tenderly_api import TenderlyClient

# -----------------------------------------------------------------------------
# Constants – update if the Balancer pool layout changes
# -----------------------------------------------------------------------------

# Tokens
GNO: ChecksumAddress = Web3.to_checksum_address("0x9c58bacc331c9aa871afd802db6379a98e80cedb")
SDAI: ChecksumAddress = Web3.to_checksum_address("0xaf204776c7245bf4147c2612bf6e5972ee483701")

# Pools (Gnosis)
BUFFER_POOL: ChecksumAddress = Web3.to_checksum_address("0x7c16f0185a26db0ae7a9377f23bc18ea7ce5d644")
FINAL_POOL: ChecksumAddress = Web3.to_checksum_address("0xd1d7fa8871d84d0e77020fc28b7cd5718c446522")

# Router selector for swapExactIn (batch router v5) – kept for reference
SWAP_EXACT_IN_SELECTOR = "0x286f580d"

# The maximum uint48 Balancer deadline used in the JS helper (2^53 − 1)
MAX_DEADLINE = 9007199254740991

# -----------------------------------------------------------------------------
# ABI loading
# -----------------------------------------------------------------------------

# In production put the full ABI JSON somewhere in your project and import here.
# We only need the function signature for encodeABI so an abbreviated ABI is fine.
BALANCER_ROUTER_ABI: List[Dict[str, Any]] = [
    {
        "type": "function",
        "name": "swapExactIn",
        "stateMutability": "payable",
        "inputs": [
            {
                "name": "paths",
                "type": "tuple[]",
                "components": [
                    {"name": "tokenIn", "type": "address"},
                    {
                        "name": "steps",
                        "type": "tuple[]",
                        "components": [
                            {"name": "pool", "type": "address"},
                            {"name": "tokenOut", "type": "address"},
                            {"name": "isBuffer", "type": "bool"},
                        ],
                    },
                    {"name": "exactAmountIn", "type": "uint256"},
                    {"name": "minAmountOut", "type": "uint256"},
                ],
            },
            {"name": "deadline", "type": "uint256"},
            {"name": "wethIsEth", "type": "bool"},
            {"name": "userData", "type": "bytes"},
        ],
        "outputs": [
            {"name": "pathAmountsOut", "type": "uint256[]"},
            {"name": "tokensOut", "type": "address[]"},
            {"name": "amountsOut", "type": "uint256[]"},
        ],
    }
]

# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

__all__ = [
    "build_sell_gno_to_sdai_swap_tx",
    "sell_gno_to_sdai",
    "parse_swap_results",
    "_search_call_trace",
]

def _search_call_trace(node: Dict[str, Any], target: str) -> Optional[Dict[str, Any]]:
    """Depth-first search for the first call to *target* in Tenderly call-trace."""
    if node.get("to", "").lower() == target.lower():
        return node
    for child in node.get("calls", []):
        found = _search_call_trace(child, target)
        if found:
            return found
    return None



def _get_router(w3: Web3, router_addr: str | None = None):
    """Return Balancer BatchRouter contract instance.

    The address is taken from the BALANCER_ROUTER_ADDRESS env var unless
    explicitly provided.
    """
    address = router_addr or os.getenv("BALANCER_ROUTER_ADDRESS")
    if address is None:
        raise EnvironmentError("Set BALANCER_ROUTER_ADDRESS env var or pass router_addr.")
    return w3.eth.contract(address=w3.to_checksum_address(address), abi=BALANCER_ROUTER_ABI)


# -----------------------------------------------------------------------------
# Build & simulate helpers
# -----------------------------------------------------------------------------

def build_sell_gno_to_sdai_swap_tx(
    w3: Web3,
    client: TenderlyClient,
    amount_in_wei: int,
    min_amount_out_wei: int,
    sender: str,
    *,
    router_addr: str | None = None,
    deadline: int = MAX_DEADLINE,
    weth_is_eth: bool = False,
    user_data: bytes = b"",
) -> Dict[str, Any]:
    """Encode swapExactIn calldata for GNO → sDAI and wrap in a Tenderly tx dict."""

    router = _get_router(w3, router_addr)

    # SwapPathStep[] – two hops
    steps = [
        # 1️⃣ GNO → buffer token (pool uses the same token addr for tokenOut)
        (
            BUFFER_POOL,  # pool address
            BUFFER_POOL,  # tokenOut address (router expects this redundancy)
            True,  # isBuffer
        ),
        # 2️⃣ buffer token → sDAI
        (
            FINAL_POOL,
            SDAI,
            False,
        ),
    ]

    # SwapPathExactAmountIn
    path = (
        GNO,  # tokenIn
        steps,
        int(amount_in_wei),
        int(min_amount_out_wei),
    )

    calldata = router.encodeABI(
        fn_name="swapExactIn",
        args=[[path], int(deadline), bool(weth_is_eth), user_data],
    )

    return client.build_tx(router.address, calldata, sender)


def sell_gno_to_sdai(
    w3: Web3,
    client: TenderlyClient,
    amount_in_wei: int,
    min_amount_out_wei: int,
    sender: str,
    *,
    router_addr: str | None = None,
) -> Optional[Dict[str, Any]]:
    """Convenience wrapper: build tx → simulate via Tenderly → pretty-print result."""

    tx = build_sell_gno_to_sdai_swap_tx(
        w3,
        client,
        amount_in_wei,
        min_amount_out_wei,
        sender,
        router_addr=router_addr,
    )

    result = client.simulate([tx])
    if result and result.get("simulation_results"):
        parse_swap_results(result["simulation_results"], w3)
    else:
        print("Simulation failed or returned no results.")
    return result


# -----------------------------------------------------------------------------
# Result parsing / pretty printing
# -----------------------------------------------------------------------------

def _wei_to_eth(value: int) -> Decimal:
    return Decimal(Web3.from_wei(value, "ether"))


def parse_swap_results(results: List[Dict[str, Any]], w3: Web3) -> Optional[Dict[str, Decimal]]:
    """Pretty-print and return {'input_amount', 'output_amount'} for each result."""
    result_dict: Optional[Dict[str, Decimal]] = None
    for idx, sim in enumerate(results):
        if sim.get("error"):
            print("Tenderly simulation error:", sim["error"].get("message", "Unknown error"))
            continue
        tx = sim.get("transaction")
        if not tx:
            print("No transaction data in result.")
            continue
        if tx.get("status") is False:
            info = tx.get("transaction_info", {})
            reason = info.get("error_message", info.get("revert_reason", "N/A"))
            print("❌ swapExactIn REVERTED. Reason:", reason)
            continue
        # ------------------------------------------------------------------ #
        # 1. Walk trace → router call                                        #
        # ------------------------------------------------------------------ #
        call_trace = tx.get("transaction_info", {}).get("call_trace", {})
        router      = _get_router(w3)
        router_call = _search_call_trace(call_trace, router.address)
        if router_call is None:
            print("Router call not found in trace.")
            continue
        # ------------------------------------------------------------------ #
        # 2. Decode call INPUT                                               #
        # ------------------------------------------------------------------ #
        func, params = router.decode_function_input(router_call["input"])
        # Extract exactAmountIn from the first path element, handling both tuple- and dict-style decodes.
        if isinstance(params, dict):
            # Grab the single positional arg ("paths") if params is a mapping
            param_val = next(iter(params.values()))
        else:
            param_val = params[0]  # positional list/tuple

        if not param_val:
            print("Decoded params empty – cannot find paths.")
            continue

        # param_val is paths: List[SwapPathExactAmountIn]
        first_path = param_val[0] if isinstance(param_val, (list, tuple)) else next(iter(param_val.values()))
        # SwapPath tuple: (tokenIn, steps, exactAmountIn, minAmountOut)
        if isinstance(first_path, (list, tuple)):
            exact_amount_in = first_path[2]
        else:
            exact_amount_in = first_path.get("exactAmountIn") or first_path.get("amountIn")

        if exact_amount_in is None:
            print("Could not extract exactAmountIn from decoded input.")
            continue

        # ------------------------------------------------------------------ #
        # 3. Decode call OUTPUT                                              #
        # ------------------------------------------------------------------ #
        decoded      = w3.codec.decode(["uint256[]", "address[]", "uint256[]"],
                                        bytes.fromhex(router_call["output"][2:]))
        output_wei   = decoded[2][0]          # amountsOut[0]
        result_dict = {
            "input_amount":  _wei_to_eth(exact_amount_in),
            "output_amount": _wei_to_eth(output_wei),
        }
        print("result_dict:", result_dict)
        balance_changes = sim.get("balance_changes") or {}
        if balance_changes:
            print("Balance changes:")
            for token_addr, diff in balance_changes.items():
                human = _wei_to_eth(abs(int(diff)))
                sign = "+" if int(diff) > 0 else "-"
                print(f"  {token_addr}: {sign}{human}")
        else:
            print("(No balance change info)")
    return result_dict




# -----------------------------------------------------------------------------
# CLI helper for quick testing –  `python -m balancer_swap --amount_in 0.1`
# -----------------------------------------------------------------------------

def _build_w3_from_env() -> Web3:
    rpc_url = os.getenv("GNOSIS_RPC_URL") or os.getenv("RPC_URL")
    if rpc_url is None:
        raise EnvironmentError("Set GNOSIS_RPC_URL or RPC_URL in environment.")
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    from web3.middleware import geth_poa_middleware

    w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    return w3


def main():  # pragma: no cover
    """Quick manual test."""
    import argparse
    from dotenv import load_dotenv

    load_dotenv()

    parser = argparse.ArgumentParser(description="Simulate GNO → sDAI swap via Tenderly")
    parser.add_argument("--amount_in", type=float, default=0.1, help="GNO amount to sell (ether equivalent)")
    parser.add_argument("--min_out", type=float, default=1.0, help="Minimum acceptable sDAI (ether equivalent)")
    args = parser.parse_args()

    sender = os.getenv("WALLET_ADDRESS") or os.getenv("SENDER_ADDRESS")
    if sender is None:
        raise EnvironmentError("Set WALLET_ADDRESS or SENDER_ADDRESS env var.")

    w3 = _build_w3_from_env()
    if not w3.is_connected():
        raise ConnectionError("Could not connect to RPC endpoint.")

    client = TenderlyClient(w3)
    amount_in_wei = w3.to_wei(Decimal(str(args.amount_in)), "ether")
    min_out_wei = w3.to_wei(Decimal(str(args.min_out)), "ether")

    result = sell_gno_to_sdai(w3, client, amount_in_wei, min_out_wei, sender)

    tx = result["simulation_results"][0]["transaction"]
    if tx.get("status") is False:
        print("Swap transaction reverted.")
    else:
        print("Swap transaction did NOT revert.")


if __name__ == "__main__":  # pragma: no cover
    main()

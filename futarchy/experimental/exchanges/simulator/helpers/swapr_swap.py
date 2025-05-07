import os
import time
from decimal import Decimal
from typing import Any, Dict, List, Tuple, Optional
from web3 import Web3
# NOTE: Assuming the ABI location is correct relative to the new structure
from futarchy.experimental.config.abis.swapr import SWAPR_ROUTER_ABI 
from .tenderly_api import TenderlyClient

w3 = Web3(Web3.HTTPProvider(os.environ["RPC_URL"]))

router_addr = w3.to_checksum_address(os.environ["SWAPR_ROUTER_ADDRESS"])
router = w3.eth.contract(address=router_addr, abi=SWAPR_ROUTER_ABI)

client = TenderlyClient(w3)


def tx_exact_in(params, sender):
    data = client.encode_exact_in(router, params)
    return client.build_tx(router.address, data, sender)


def tx_exact_out(params, sender):
    data = client.encode_exact_out(router, params)
    return client.build_tx(router.address, data, sender)


# --------------------------------------------------------------------------- #
# Enhanced builder helpers mirroring balancer_swap.py                         #
# --------------------------------------------------------------------------- #

__all__ = [
    "w3",
    "client",
    "build_exact_in_tx",
    "build_exact_out_tx",
    "simulate_exact_in",
    "simulate_exact_out",
    "parse_swap_results",
    # legacy wrappers
    "tx_exact_in",
    "tx_exact_out",
]


def _deadline(seconds: int = 600) -> int:
    """Return a unix timestamp ``seconds`` in the future."""

    return int(time.time()) + seconds


def _encode_exact_in(
    token_in: str,
    token_out: str,
    sender: str,
    amount_in_wei: int,
    amount_out_min_wei: int,
    sqrt_price_limit: int = 0,
) -> str:
    params: Tuple = (
        w3.to_checksum_address(token_in),
        w3.to_checksum_address(token_out),
        w3.to_checksum_address(sender),
        _deadline(),
        int(amount_in_wei),
        int(amount_out_min_wei),
        int(sqrt_price_limit),
    )
    return client.encode_exact_in(router, params)


def _encode_exact_out(
    token_in: str,
    token_out: str,
    sender: str,
    amount_out_wei: int,
    amount_in_max_wei: int,
    sqrt_price_limit: int = 0,
) -> str:
    params: Tuple = (
        w3.to_checksum_address(token_in),
        w3.to_checksum_address(token_out),
        500,  # fee tier (SwapR uses 0.05% pools on Gnosis)
        w3.to_checksum_address(sender),
        _deadline(),
        int(amount_out_wei),
        int(amount_in_max_wei),
        int(sqrt_price_limit),
    )
    return client.encode_exact_out(router, params)


def build_exact_in_tx(
    token_in: str,
    token_out: str,
    amount_in_wei: int,
    amount_out_min_wei: int,
    sender: str,
    *,
    sqrt_price_limit: int = 0,
) -> Dict[str, Any]:
    """Return Tenderly-ready tx dict for exactInputSingle."""

    data = _encode_exact_in(
        token_in, token_out, sender, amount_in_wei, amount_out_min_wei, sqrt_price_limit
    )
    return client.build_tx(router.address, data, sender)


def build_exact_out_tx(
    token_in: str,
    token_out: str,
    amount_out_wei: int,
    amount_in_max_wei: int,
    sender: str,
    *,
    sqrt_price_limit: int = 0,
) -> Dict[str, Any]:
    """Return Tenderly-ready tx dict for exactOutputSingle."""

    data = _encode_exact_out(
        token_in, token_out, sender, amount_out_wei, amount_in_max_wei, sqrt_price_limit
    )
    return client.build_tx(router.address, data, sender)


# Convenience wrappers ------------------------------------------------------- #


def simulate_exact_in(*args, **kwargs):
    """Build **and** simulate an exact-in swap via Tenderly."""

    tx = build_exact_in_tx(*args, **kwargs)
    return client.simulate([tx])


def simulate_exact_out(*args, **kwargs):
    """Build **and** simulate an exact-out swap via Tenderly."""

    tx = build_exact_out_tx(*args, **kwargs)
    return client.simulate([tx])


# Result parsing ------------------------------------------------------------- #


def _wei_to_eth(value: int) -> Decimal:
    return Decimal(Web3.from_wei(value, "ether"))


def parse_swap_results(results: List[Dict[str, Any]], w3_inst: Optional[Web3] = None) -> None:
    """Pretty-print Tenderly simulation results (compatible with balancer helper)."""

    w3_local = w3_inst or w3
    for idx, sim in enumerate(results):
        if len(results) == 1:
            print(f"\n--- SwapR Simulation Result ---")
        else:
            print(f"\n--- SwapR Simulation Result #{idx + 1} ---")

        if sim.get("error"):
            print("Tenderly simulation error:", sim["error"].get("message", "Unknown error"))
            continue

        tx_resp = sim.get("transaction") or {}
        if tx_resp.get("status") is False:
            info = tx_resp.get("transaction_info", {})
            print("❌ transaction REVERTED:", info.get("error_message", info.get("revert_reason", "N/A")))
            continue

        print("✅ swap succeeded.")

        # Attempt to decode amountOut from call trace output
        call_trace = tx_resp.get("transaction_info", {}).get("call_trace", {})
        out_hex = call_trace.get("output")
        if out_hex and out_hex != "0x":
            try:
                amount_out_wei = int(out_hex[2:66], 16)
                print("  amountOut:", _wei_to_eth(amount_out_wei))
            except Exception:  # noqa: BLE001
                pass

        # Print balance changes when available
        for token, diff in (sim.get("balance_changes") or {}).items():
            sign = "+" if int(diff) > 0 else "-"
            human = _wei_to_eth(abs(int(diff)))
            print(f"  {token}: {sign}{human}")

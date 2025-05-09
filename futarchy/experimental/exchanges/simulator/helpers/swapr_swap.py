import os
import time
import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional
from web3 import Web3
# NOTE: Assuming the ABI location is correct relative to the new structure
from futarchy.experimental.config.abis.swapr import SWAPR_ROUTER_ABI 
from .tenderly_api import TenderlyClient

w3 = Web3(Web3.HTTPProvider(os.environ["RPC_URL"]))

router_addr = w3.to_checksum_address(os.environ["SWAPR_ROUTER_ADDRESS"])
router = w3.eth.contract(address=router_addr, abi=SWAPR_ROUTER_ABI)

client = TenderlyClient(w3)

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logger = logging.getLogger(__name__)

def tx_exact_in(params, sender):
    data = router.encodeABI(fn_name="exactInputSingle", args=[params])
    return client.build_tx(router.address, data, sender)


def tx_exact_out(params, sender):
    data = router.encodeABI(fn_name="exactOutputSingle", args=[params])
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

    params = (
        w3.to_checksum_address(token_in),
        w3.to_checksum_address(token_out),
        w3.to_checksum_address(sender),
        _deadline(),
        int(amount_in_wei),
        int(amount_out_min_wei),
        int(sqrt_price_limit),
    )
    data = router.encodeABI(fn_name="exactInputSingle", args=[params])
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

    params = (
        w3.to_checksum_address(token_in),
        w3.to_checksum_address(token_out),
        500,  # 0.05 % fee pool
        w3.to_checksum_address(sender),
        _deadline(),
        int(amount_out_wei),
        int(amount_in_max_wei),
        int(sqrt_price_limit),
    )
    data = router.encodeABI(fn_name="exactOutputSingle", args=[params])
    return client.build_tx(router.address, data, sender)


# Convenience wrappers ------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# Internal helpers                                                            #
# --------------------------------------------------------------------------- #

def _search_call_trace(node: Dict[str, Any], target: str) -> Optional[Dict[str, Any]]:
    """Recursively walk Tenderly's call-trace until the first call to *target*."""
    if node.get("to", "").lower() == target.lower():
        return node
    for child in node.get("calls", []):
        found = _search_call_trace(child, target)
        if found:
            return found
    return None


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


def parse_swap_results(
    results: List[Dict[str, Any]],
    w3_inst: Optional[Web3] = None,
    label: Optional[str] = None,
    fixed: str = "in",
) -> Optional[Dict[str, Decimal]]:
    """Pretty-print simulation results.

    For both ``exactInputSingle`` **and** ``exactOutputSingle`` swaps return
    ``{'input_amount': Decimal, 'output_amount': Decimal}``.
    """
    w3_local = w3_inst or w3
    result_dict: Optional[Dict[str, Decimal]] = None
    for idx, sim in enumerate(results):
        if label:
            header = label
        elif len(results) == 1:
            header = "SwapR Simulation Result"
        else:
            header = f"SwapR Simulation Result #{idx + 1}"

        logger.debug("--- %s ---", header)

        if sim.get("error"):
            logger.debug("Tenderly simulation error: %s", sim["error"].get("message", "Unknown error"))
            continue

        tx_resp = sim.get("transaction") or {}
        if tx_resp.get("status") is False:
            info = tx_resp.get("transaction_info", {})
            logger.debug("transaction REVERTED. Reason: %s", info.get("error_message", info.get("revert_reason", "N/A")))
            continue

        logger.debug("swap succeeded.")

        # Attempt to decode returned amount based on swap kind
        call_trace = tx_resp.get("transaction_info", {}).get("call_trace", {})
        out_hex = call_trace.get("output")
        ret_wei: Optional[int] = None
        if out_hex and out_hex != "0x":
            try:
                ret_wei = int(out_hex[2:66], 16)
                human_out = _wei_to_eth(ret_wei)
                if fixed == "in":
                    logger.debug("  amountOut: %s", human_out)
                else:
                    logger.debug("  amountIn: %s", human_out)
            except Exception:  # noqa: BLE001
                pass

        # ------------------------------------------------------------------ #
        # 1. Locate the router call in the nested trace                      #
        # ------------------------------------------------------------------ #
        router_call = _search_call_trace(call_trace, router.address)
        if router_call is None:
            logger.debug("router call NOT found – cannot decode input")
            continue

        # ------------------------------------------------------------------ #
        # 2. Decode the router call input/output                             #
        # ------------------------------------------------------------------ #
        call_input = router_call.get("input")
        if call_input and call_input != "0x":
            logger.debug("router_call input: %s…", call_input[:10])
            try:
                func, params = router.decode_function_input(call_input)
                logger.debug("decoded function: %s", func.fn_name)
                # The decode result can be either a list/tuple or a dict:
                inner = (
                    params[0]                       # positional (tuple/list)
                    if not isinstance(params, dict)
                    else next(iter(params.values()))  # dict -> grab the single struct
                )

                if func.fn_name == "exactInputSingle":
                    input_wei = inner[4] if isinstance(inner, (list, tuple)) else inner["amountIn"]
                    ret_wei    = int(router_call.get("output", "0x")[2:66], 16)
                    result_dict = {
                        "input_amount":  _wei_to_eth(input_wei),
                        "output_amount": _wei_to_eth(ret_wei),
                    }

                elif func.fn_name == "exactOutputSingle":
                    output_wei = inner[5] if isinstance(inner, (list, tuple)) else inner["amountOut"]
                    ret_wei    = int(router_call.get("output", "0x")[2:66], 16)
                    result_dict = {
                        "input_amount":  _wei_to_eth(ret_wei),  # actual cost
                        "output_amount": _wei_to_eth(output_wei),
                    }

                # Debug: show the struct we just parsed
                logger.debug("inner struct: %s", inner)
                logger.debug("result_dict: %s", result_dict)

            except Exception as e:
                logger.debug("decode_function_input exception: %s", e)

        # Print balance changes when available
        for token, diff in (sim.get("balance_changes") or {}).items():
            sign = "+" if int(diff) > 0 else "-"
            human = _wei_to_eth(abs(int(diff)))
            logger.debug("  %s: %s%s", token, sign, human)
    logger.debug("result_dict final: %s", result_dict)
    return result_dict

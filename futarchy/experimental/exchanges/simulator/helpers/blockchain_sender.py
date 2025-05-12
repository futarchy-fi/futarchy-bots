import os
import sys
from web3 import Web3
from eth_account import Account
from typing import Optional

# Use the same env vars that the rest of the code base already relies on.
RPC_URL = os.getenv("RPC_URL")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")

w3 = Web3(Web3.HTTPProvider(RPC_URL))
acct = Account.from_key(PRIVATE_KEY)

__all__ = ["w3", "acct", "send_tenderly_tx_onchain"]


def send_tenderly_tx_onchain(tenderly_tx: dict, value: int = 0, nonce: Optional[int] = None) -> str:
    """
    Sign and broadcast a transaction that was built for Tenderly simulation.

    Parameters
    ----------
    tenderly_tx : dict
        The dict returned by any ``build_*_tx`` helper
        (must contain ``"to"`` and ``"input"`` keys).
    value : int, optional
        Ether value to forward with the tx (wei).  Default is 0.
    nonce : int, optional
        Optional nonce to control sequence. If not provided, will use the current transaction count.

    Returns
    -------
    str
        The transaction hash as a hex string.
    """
    # --- Fee calculation (EIP-1559) ----------------------------------------
    latest_block = w3.eth.get_block("latest")
    base_fee = latest_block.get("baseFeePerGas", w3.eth.gas_price)
    priority_fee = Web3.to_wei(2, "gwei")  # 2 gwei tip
    max_fee = base_fee + priority_fee * 2  # generous cap

    tx = {
        "to": tenderly_tx["to"],
        "data": tenderly_tx["input"],
        "value": value,
        "nonce": nonce if nonce is not None else w3.eth.get_transaction_count(acct.address),
        "maxPriorityFeePerGas": priority_fee,
        "maxFeePerGas": max_fee,
        "chainId": w3.eth.chain_id,
        # 'type': 2  # explicit EIP-1559, web3 auto-sets when fields present
    }

    try:
        tx["gas"] = w3.eth.estimate_gas(
            {
                "to": tx["to"],
                "from": acct.address,
                "data": tx["data"],
                "value": value,
            }
        )
    except Exception as err:  # fallback on ANY estimation failure
        print("estimate_gas failed, using 700_000 fallback ->", err)
        tx["gas"] = 700_000

    signed_tx = acct.sign_transaction(tx)
    return w3.eth.send_raw_transaction(signed_tx.rawTransaction).hex()


# --------------------------------------------------------------------------- #
# Minimal CLI helper                                                           #
# --------------------------------------------------------------------------- #


def main() -> None:  # noqa: D401
    """Quick-and-dirty CLI for SwapR exactInputSingle broadcast.

    Usage::

        python -m futarchy.experimental.exchanges.simulator.helpers.blockchain_sender \
            swapr_exact_in <token_in> <token_out> <amount_in_wei> <amount_out_min_wei>
    """
    # Lazily import to avoid circular deps when used as lib
    from futarchy.experimental.exchanges.simulator.helpers.swapr_swap import (
        build_exact_in_tx,
        parse_broadcasted_swap_results,
        w3 as local_w3,
    )

    if len(sys.argv) < 2 or sys.argv[1] != "swapr_exact_in":
        print("Nothing to do – pass 'swapr_exact_in' for SwapR exactInputSingle broadcast.")
        return

    if len(sys.argv) != 6:
        print(
            "Usage: swapr_exact_in <token_in> <token_out> <amount_in_wei> <amount_out_min_wei>",
        )
        return

    _, _flag, token_in, token_out, amount_in, amount_out_min = sys.argv

    token_in  = local_w3.to_checksum_address(token_in)
    token_out = local_w3.to_checksum_address(token_out)

    amount_in_wei       = int(amount_in)
    amount_out_min_wei  = int(amount_out_min)

    # ------------------------------------------------------------------ #
    # Build & broadcast                                                 #
    # ------------------------------------------------------------------ #
    tx_dict = build_exact_in_tx(
        token_in,
        token_out,
        amount_in_wei,
        amount_out_min_wei,
        acct.address,
    )

    print("Broadcasting…")
    tx_hash = send_tenderly_tx_onchain(tx_dict)
    print("Tx hash:", tx_hash)

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    print("Status:", receipt.status)

    # ------------------------------------------------------------------ #
    # Parse on-chain result                                             #
    # ------------------------------------------------------------------ #
    result = parse_broadcasted_swap_results(tx_hash)
    print("Swap result:", result)


if __name__ == "__main__":
    main()

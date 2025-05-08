import os, time
from decimal import Decimal
from eth_account import Account
from .helpers.swapr_swap import (
    w3,
    client,
    build_exact_in_tx,
    build_exact_out_tx,
    parse_swap_results as parse_swapr_results,
)
from .helpers.split_position import build_split_tx
from .helpers.merge_position import build_merge_tx
from .helpers.balancer_swap import build_sell_gno_to_sdai_swap_tx, parse_swap_results

acct = Account.from_key(os.environ["PRIVATE_KEY"])

token_yes_in = w3.to_checksum_address(os.environ["SWAPR_SDAI_YES_ADDRESS"])
token_yes_out = w3.to_checksum_address(os.environ["SWAPR_GNO_YES_ADDRESS"])
token_no_in = w3.to_checksum_address(os.environ["SWAPR_SDAI_NO_ADDRESS"])
token_no_out = w3.to_checksum_address(os.environ["SWAPR_GNO_NO_ADDRESS"])

# --- Futarchy splitPosition parameters ---------------------------------------
router_addr = w3.to_checksum_address(os.environ["FUTARCHY_ROUTER_ADDRESS"])
proposal_addr = w3.to_checksum_address(os.environ["FUTARCHY_PROPOSAL_ADDRESS"])
collateral_addr = w3.to_checksum_address(os.environ["SDAI_TOKEN_ADDRESS"])
gno_collateral_addr = w3.to_checksum_address(os.environ["GNO_TOKEN_ADDRESS"])

def add_conditional_sdai_liquidation_steps(
    liquidate_conditional_sdai_amount,
    handle_liquidate,
    handle_buy_sdai_yes,
    handle_merge_conditional_sdai,
):
    """
    Returns a list of (tx, handler) for conditional sDAI liquidation.
    To be appended to the steps list.
    """
    steps = []
    if liquidate_conditional_sdai_amount and liquidate_conditional_sdai_amount > 0:
        liq_tx = build_liquidate_remaining_conditional_sdai_tx(
            liquidate_conditional_sdai_amount, True
        )
        if liq_tx:
            steps.append((liq_tx, handle_liquidate))
    else:
        liq_txs = build_liquidate_remaining_conditional_sdai_tx(
            -liquidate_conditional_sdai_amount, False
        )
        if liq_txs:
            steps += [
                (liq_txs[0], handle_buy_sdai_yes),
                (liq_txs[1], handle_merge_conditional_sdai),
            ]
    return steps

def build_step_1_swap_txs(split_amount_in_wei, gno_amount_in_wei, price=100):
    if gno_amount_in_wei is None:
        deadline = int(time.time()) + 600
        amount_in_max = int(split_amount_in_wei * 1.2)
        amount_out_expected = int(split_amount_in_wei / price)
        amount_out_min = int(amount_out_expected * 0.9)
        sqrt_price_limit = 0

        return [
            build_exact_in_tx(
                token_yes_in, token_yes_out, split_amount_in_wei, amount_out_min, acct.address
            ),
            build_exact_in_tx(
                token_no_in, token_no_out, split_amount_in_wei, amount_out_min, acct.address
            ),
        ]
    else:
        deadline = int(time.time()) + 600
        amount_in_max = int(split_amount_in_wei * 1.2)
        amount_out_expected = gno_amount_in_wei
        amount_out_min = int(amount_out_expected * 0.9)
        sqrt_price_limit = 0

        return [
            build_exact_out_tx(
                token_yes_in, token_yes_out, amount_out_expected, amount_in_max, acct.address
            ),
            build_exact_out_tx(
                token_no_in, token_no_out, amount_out_expected, amount_in_max, acct.address
            ),
        ]


def build_step_2_merge_tx(gno_amount_in_wei):
    """Return Tenderly transaction dict for FutarchyRouter.mergePositions."""
    return build_merge_tx(
        w3,
        client,
        router_addr,
        proposal_addr,
        gno_collateral_addr,
        int(gno_amount_in_wei),
        acct.address,
    )


# --------------------------------------------------------------------------- #
# Simple helper: liquidate conditional sDAI (YES) back to plain sDAI          #
# --------------------------------------------------------------------------- #

def build_liquidate_remaining_conditional_sdai_tx(amount: float, is_yes: bool):
    """Return Tenderly tx dict swapping sDAI-Yes → sDAI via SwapR exact-in.

    If *is_yes* is False, this is a no-op and returns ``None``.
    """
    if is_yes:
        amount_in_wei = w3.to_wei(Decimal(amount), "ether")
        min_amount_out_wei = 1  # minimal out to avoid reverting on 0

        in_token = w3.to_checksum_address(os.environ["SWAPR_SDAI_YES_ADDRESS"])
        out_token = w3.to_checksum_address(os.environ["SDAI_TOKEN_ADDRESS"])

        return build_exact_in_tx(
            in_token,
            out_token,
            amount_in_wei,
            int(amount_in_wei * 0.1),
            acct.address,
            sqrt_price_limit=0,
        )
    else:
        # Build and return two txs:
        #   1️⃣ buy exact-out <amount> sDAI-YES with plain sDAI
        #   2️⃣ merge the freshly bought sDAI-YES back into plain sDAI
        amount_out_yes_wei = w3.to_wei(Decimal(amount), "ether")
        max_in_sdai_wei = int(amount_out_yes_wei * 1.2)

        buy_tx = build_exact_out_tx(
            w3.to_checksum_address(os.environ["SDAI_TOKEN_ADDRESS"]),   # tokenIn  (sDAI)
            w3.to_checksum_address(os.environ["SWAPR_SDAI_YES_ADDRESS"]),# tokenOut (sDAI-YES)
            amount_out_yes_wei,                                          # exact-out
            max_in_sdai_wei,                                             # slippage buffer
            acct.address,
        )

        merge_tx = build_merge_tx(
            w3,
            client,
            router_addr,
            proposal_addr,
            collateral_addr,          # merge sDAI collateral
            amount_out_yes_wei,
            acct.address,
        )

        return [buy_tx, merge_tx]


# Adjust collateral amount to split as needed (currently hard-coded to 1 ether)
def get_gno_yes_and_no_amounts_from_sdai(split_amount, gno_amount=None, liquidate_conditional_sdai_amount=None, price=100):
    split_amount_in_wei = w3.to_wei(Decimal(split_amount), "ether")
    if gno_amount is not None:
        gno_amount_in_wei = w3.to_wei(Decimal(gno_amount), "ether")
    else:
        gno_amount_in_wei = None

    # Build the splitPosition tx dict (to be simulated by Tenderly)
    split_tx = build_split_tx(
        w3,
        client,
        router_addr,
        proposal_addr,
        collateral_addr,
        split_amount_in_wei,
        acct.address,
    )

    deadline = int(time.time()) + 600
    amount_in_max = int(split_amount_in_wei * 1.2)
    amount_out_expected = int(split_amount_in_wei / price)
    amount_out_min = int(amount_out_expected * 0.9)
    sqrt_price_limit = 0

    # If user supplied GNO to sell, build Balancer swap tx first
    gno_to_sdai_txs = []
    if gno_amount_in_wei:
        # Require at least 1 wei out – caller can adjust price slippage externally
        gno_to_sdai_txs.append(
            build_sell_gno_to_sdai_swap_tx(
                w3,
                client,
                gno_amount_in_wei,
                1,  # minAmountOut = 1 wei (effectively no slippage protection)
                acct.address,
            )
        )

    # ------------------------------------------------------------------
    # 1️⃣  Define handlers FIRST so we can reference them in the steps list
    # ------------------------------------------------------------------

    def handle_split(idx, sim):
        print("SplitPosition tx parsed – nothing to extract.")

    def handle_yes_swap(idx, sim):
        """Swap of GNO-YES → sDAI-YES (exact-out)."""
        nonlocal amount_out_yes_wei
        parse_swapr_results([sim], label="SwapR YES (exact-out)", fixed="out")
        extracted = extract_return(sim, gno_amount_in_wei, "out")
        if extracted is not None:
            amount_out_yes_wei = extracted

    def handle_no_swap(idx, sim):
        """Swap of GNO-NO → sDAI-NO (exact-out)."""
        nonlocal amount_out_no_wei
        parse_swapr_results([sim], label="SwapR NO  (exact-out)", fixed="out")
        extracted = extract_return(sim, gno_amount_in_wei, "out")
        if extracted is not None:
            amount_out_no_wei = extracted

    def handle_merge(idx, sim):
        print("MergePositions tx parsed – nothing to extract.")

    def handle_liquidate(idx, sim):
        parse_swapr_results([sim], label="SwapR Liquidate YES→sDAI (exact-in)", fixed="in")

    def handle_buy_sdai_yes(idx, sim):
        parse_swapr_results([sim], label="SwapR buy sDAI-YES (exact-out)", fixed="out")

    def handle_merge_conditional_sdai(idx, sim):
        print("Merge conditional sDAI positions parsed – nothing to extract.")

    def handle_balancer(idx, sim):
        parse_swap_results([sim], w3)

    # ------------------------------------------------------------------
    # 2️⃣  Build the *steps* list declaratively: (tx_dict, handler) pairs
    # ------------------------------------------------------------------

    steps: list[tuple[dict, callable]] = []

    # Split
    steps.append((split_tx, handle_split))

    # YES / NO swaps (2 txs)
    yes_tx, no_tx = build_step_1_swap_txs(split_amount_in_wei, gno_amount_in_wei, price)
    steps.append((yes_tx, handle_yes_swap))
    steps.append((no_tx, handle_no_swap))

    # Merge
    merge_tx = build_merge_tx(
        w3,
        client,
        router_addr,
        proposal_addr,
        gno_collateral_addr,
        int(gno_amount_in_wei) if gno_amount_in_wei else 0,
        acct.address,
    )
    steps.append((merge_tx, handle_merge))

    # Optional liquidation swap
    steps += add_conditional_sdai_liquidation_steps(
        liquidate_conditional_sdai_amount,
        handle_liquidate,
        handle_buy_sdai_yes,
        handle_merge_conditional_sdai,
    )

    # Optional Balancer swap (sell GNO → sDAI) – may be empty
    if gno_to_sdai_txs:
        steps.append((gno_to_sdai_txs[0], handle_balancer))

    # ------------------------------------------------------------------
    # 3️⃣  Execute simulation + dispatch handlers
    # ------------------------------------------------------------------

    bundle = [tx for tx, _ in steps]

    print("--- Prepared Bundle ---")
    print(bundle)

    result = client.simulate(bundle)

    # Initialize placeholders for the swap outputs we care about
    amount_out_yes_wei = None  # From second simulation (GNO-YES → sDAI-YES)
    amount_out_no_wei = None  # From third simulation (GNO-NO  → sDAI-NO)

    # Helper to decode uint256 output and pretty print
    def extract_return(sim, amount_in_or_out_wei_local, fixed_kind):
        tx = sim.get("transaction", {})
        call_trace = tx.get("transaction_info", {}).get("call_trace", {})
        output_hex = call_trace.get("output")
        if output_hex and output_hex != "0x":
            try:
                returned_amount_wei = int(output_hex[2:], 16)
            except ValueError:
                return None

            returned_amount = w3.from_wei(returned_amount_wei, "ether")

            if fixed_kind == "in":
                print("  Simulated amountOut:", returned_amount)
                input_amount = w3.from_wei(amount_in_or_out_wei_local, "ether")
                price = Decimal(returned_amount) / Decimal(input_amount)
            else:
                print("  Simulated amountIn:", returned_amount)
                output_amount = w3.from_wei(amount_in_or_out_wei_local, "ether")
                price = Decimal(output_amount) / Decimal(returned_amount)

            print("  Simulated price:", price)
            return returned_amount_wei
        print("  No output data returned from simulation.")
        return None

    if result and result.get("simulation_results"):
        sims = result["simulation_results"]

        for idx, sim in enumerate(sims):
            print(f"\n--- Simulation Result #{idx + 1} ---")
            if sim.get("error"):
                print("Tenderly simulation error:", sim["error"].get("message", "Unknown error"))
                continue

            tx = sim.get("transaction")
            if not tx:
                print("No transaction data in result.")
                continue
            if tx.get("status") is False:
                print("Transaction REVERTED.")
                continue
            print("Swap transaction did NOT revert.")

            # Call paired handler for this step
            if idx < len(steps):
                _, handler = steps[idx]
                handler(idx, sim)
            else:
                print("No handler defined for this tx.")
    else:
        print("Simulation failed or returned no results.")

    # Return simulated output amounts for GNO-YES and GNO-NO swaps
    return {
        "amount_out_yes": w3.from_wei(amount_out_yes_wei, "ether") if amount_out_yes_wei else None,
        "amount_out_no": w3.from_wei(amount_out_no_wei, "ether") if amount_out_no_wei else None,
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 4:
        print(
            "Usage: python -m futarchy.experimental.exchanges.simulator.simulator <amount> <gno_amount> <liquidate_conditional_sdai_amount>"
        )
        sys.exit(1)
    amount = float(sys.argv[1])
    gno_amount = float(sys.argv[2])
    liquidate_conditional_sdai_amount = float(sys.argv[3])
    result = get_gno_yes_and_no_amounts_from_sdai(amount, gno_amount, liquidate_conditional_sdai_amount)
    print(
        "(amount_out_yes, amount_out_no) = ",
        (result["amount_out_yes"], result["amount_out_no"]),
    )
# python -m futarchy.experimental.exchanges.simulator.simulator <amount> <gno_amount> <liquidate_conditional_sdai_amount>

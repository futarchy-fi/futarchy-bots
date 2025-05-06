import os, time
from decimal import Decimal
from eth_account import Account
from .swapr_swap import w3, client, tx_exact_in, tx_exact_out
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


def build_step_1_swap_txs(split_amount_in_wei, gno_amount_in_wei, price=100):
    if gno_amount_in_wei is None:
        deadline = int(time.time()) + 600
        amount_in_max = int(split_amount_in_wei * 1.2)
        amount_out_expected = int(split_amount_in_wei / price)
        amount_out_min = int(amount_out_expected * 0.9)
        sqrt_price_limit = 0

        params_yes_in = (
            token_yes_in,
            token_yes_out,
            acct.address,
            deadline,
            split_amount_in_wei,
            amount_out_min,
            sqrt_price_limit,
        )
        params_no_in = (
            token_no_in,
            token_no_out,
            acct.address,
            deadline,
            split_amount_in_wei,
            amount_out_min,
            sqrt_price_limit,
        )
        return [
            tx_exact_in(params_yes_in, acct.address),
            tx_exact_in(params_no_in, acct.address),
        ]
    else:
        deadline = int(time.time()) + 600
        amount_in_max = int(split_amount_in_wei * 1.2)
        amount_out_expected = gno_amount_in_wei
        amount_out_min = int(amount_out_expected * 0.9)
        sqrt_price_limit = 0

        params_yes_out = (
            token_yes_in,
            token_yes_out,
            500,
            acct.address,
            deadline,
            amount_out_expected,
            amount_in_max,
            sqrt_price_limit,
        )

        params_no_out = (
            token_no_in,
            token_no_out,
            500,
            acct.address,
            deadline,
            amount_out_expected,
            amount_in_max,
            sqrt_price_limit,
        )
        return [
            tx_exact_out(params_yes_out, acct.address),
            tx_exact_out(params_no_out, acct.address),
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


# Adjust collateral amount to split as needed (currently hard-coded to 1 ether)
def get_gno_yes_and_no_amounts_from_sdai(split_amount, gno_amount=None, price=100):
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

    params_yes_in = (
        token_yes_in,
        token_yes_out,
        acct.address,
        deadline,
        split_amount_in_wei,
        amount_out_min,
        sqrt_price_limit,
    )
    params_no_in = (
        token_no_in,
        token_no_out,
        acct.address,
        deadline,
        split_amount_in_wei,
        amount_out_min,
        sqrt_price_limit,
    )

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

    # Final bundle – optionally sell GNO for sDAI first, then splitPosition, swaps, merge
    bundle = ([
            split_tx,
        ]
        + build_step_1_swap_txs(split_amount_in_wei, gno_amount_in_wei, price)
        + [
            build_merge_tx(
                w3,
                client,
                router_addr,
                proposal_addr,
                gno_collateral_addr,
                int(gno_amount_in_wei) if gno_amount_in_wei else 0,
                acct.address,
            )
        ]
        + gno_to_sdai_txs
    )

    print(f"--- Prepared Bundle ---")
    print(bundle)

    result = client.simulate(bundle)

    # Initialize placeholders for the swap outputs we care about
    amount_out_yes_wei = None  # From second simulation (GNO-YES -> sDAI-YES)
    amount_out_no_wei = None  # From third simulation (GNO-NO  -> sDAI-NO)

    # --- Simple parsing of simulation results ---
    if result and result.get("simulation_results"):
        sims = result["simulation_results"]
        param_list = [params_yes_in, params_no_in]

        for idx, swap_result in enumerate(sims):
            print(f"\n--- Simulation Result #{idx+1} ---")

            if swap_result.get("error"):
                print(
                    "Tenderly simulation error:",
                    swap_result["error"].get("message", "Unknown error"),
                )
                print("Full error details:", swap_result["error"])
                continue

            tx = swap_result.get("transaction")
            if not tx:
                print("No transaction data in result.")
                continue

            if tx.get("status") is False:
                tx_info = tx.get("transaction_info", {})
                print("Swap transaction REVERTED.")
                print(
                    "  Revert reason:",
                    tx_info.get("error_message", tx_info.get("revert_reason", "N/A")),
                )
                continue

            # Successful transaction
            print("Swap transaction did NOT revert.")

            # If this is the Balancer swap (last tx of bundle when gno swap present),
            # delegate to the dedicated parser for clearer output and skip quantity extraction.
            if gno_to_sdai_txs and idx == len(sims) - 1:
                parse_swap_results([swap_result], w3)
                continue

            tx_info = tx.get("transaction_info", {})
            call_trace = tx_info.get("call_trace", {})
            output_hex = call_trace.get("output")

            # We only care about the two Swapr swaps that have uint256 output (YES and NO)
            if idx < len(param_list) and output_hex and output_hex != "0x":
                try:
                    amount_out_wei = int(output_hex, 16)
                except ValueError:
                    amount_out_wei = None

                if amount_out_wei:
                    # Store outputs
                    if idx == 0:
                        amount_out_yes_wei = amount_out_wei
                    elif idx == 1:
                        amount_out_no_wei = amount_out_wei

                    amount_in_wei_local = param_list[idx][4]
                    print(
                        "  Simulated amountOut:",
                        w3.from_wei(amount_out_wei, "ether"),
                        token_yes_out if idx == 0 else token_no_out,
                    )
                    price = Decimal(w3.from_wei(amount_out_wei, "ether")) / Decimal(
                        w3.from_wei(amount_in_wei_local, "ether")
                    )
                    print("  Simulated price:", price)
                else:
                    print("  No output data returned from simulation.")
            else:
                print("  Output not parsed for this tx.")
    else:
        print("Simulation failed or returned no results.")

    # Return simulated output amounts for GNO-YES and GNO-NO swaps

    return {
        "amount_out_yes": w3.from_wei(amount_out_yes_wei, "ether"),
        "amount_out_no": w3.from_wei(amount_out_no_wei, "ether"),
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print(
            "Usage: python -m futarchy.experimental.exchanges.simulator.simulator <amount> <gno_amount>"
        )
        sys.exit(1)
    amount = float(sys.argv[1])
    gno_amount = float(sys.argv[2])
    result = get_gno_yes_and_no_amounts_from_sdai(amount, gno_amount)
    print(
        "(amount_out_yes, amount_out_no) = ",
        (result["amount_out_yes"], result["amount_out_no"]),
    )
# python -m futarchy.experimental.exchanges.simulator.simulator <amount> <gno_amount>

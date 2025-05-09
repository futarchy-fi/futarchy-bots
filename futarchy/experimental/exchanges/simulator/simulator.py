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
            -(liquidate_conditional_sdai_amount or 0), False
        )
        if liq_txs:
            steps += [
                (liq_txs[0], handle_buy_sdai_yes),
                (liq_txs[1], handle_merge_conditional_sdai),
            ]
    return steps

def build_step_1_swap_steps(split_amount_in_wei, gno_amount_in_wei, price=1000):
    if gno_amount_in_wei is None:
        deadline = int(time.time()) + 600
        amount_in_max = int(split_amount_in_wei * 1.2)
        # amount_out_expected = int(split_amount_in_wei / price)
        amount_out_expected = 83891929876473596
        amount_out_min = int(amount_out_expected * 0.9)
        sqrt_price_limit = 0

        yes_tx = build_exact_in_tx(
            token_yes_in, token_yes_out, split_amount_in_wei, amount_out_min, acct.address
        )
        no_tx = build_exact_in_tx(
            token_no_in, token_no_out, split_amount_in_wei, amount_out_min, acct.address
        )
        return [
            (yes_tx, handle_swap("yes", "in")),
            (no_tx, handle_swap("no", "in")),
        ]
    else:
        deadline = int(time.time()) + 600
        amount_in_max = int(split_amount_in_wei * 1.2)
        amount_out_expected = gno_amount_in_wei
        amount_out_min = int(amount_out_expected * 0.9)
        sqrt_price_limit = 0

        yes_tx = build_exact_out_tx(
            token_yes_in, token_yes_out, amount_out_expected, amount_in_max, acct.address
        )
        no_tx = build_exact_out_tx(
            token_no_in, token_no_out, amount_out_expected, amount_in_max, acct.address
        )
        return [
            (yes_tx, handle_swap("yes", "out")),
            (no_tx, handle_swap("no", "out")),
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
            int(amount_in_wei * 0.01),
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
def handle_split(state, sim):
    return state

def handle_yes_swap(state, sim):
    data = parse_swapr_results([sim], label="SwapR YES (exact-out)", fixed="out")
    returned_amount_wei = extract_return(sim, None, "out")
    if returned_amount_wei is not None:
        state["amount_out_yes_wei"] = returned_amount_wei
    return state

def handle_no_swap(state, sim):
    data = parse_swapr_results([sim], label="SwapR NO  (exact-out)", fixed="out")
    returned_amount_wei = extract_return(sim, None, "out")
    if returned_amount_wei is not None:
        state["amount_out_no_wei"] = returned_amount_wei
    return state

def handle_merge(state, sim):
    return state

def handle_liquidate(state, sim):
    data = parse_swapr_results([sim], label="SwapR Liquidate YES→sDAI (exact-in)", fixed="in")
    if data:
        state["sdai_out"] += data["output_amount"]
    return state

def handle_buy_sdai_yes(state, sim):
    data = parse_swapr_results([sim], label="SwapR buy sDAI-YES (exact-out)", fixed="out")
    return state

def handle_merge_conditional_sdai(state, sim):
    return state

def handle_balancer(state, sim):
    data = parse_swap_results([sim], w3)
    if data:
        state["sdai_out"] += data["output_amount"]
    return state

def handle_swap(label_kind: str, fixed_kind: str):
    """Return a swap handler closure for either YES or NO leg.

    *label_kind* must be ``"yes"`` or ``"no"`` and *fixed_kind* ``"in"`` or ``"out"``.
    The closure updates the corresponding ``state`` field with the amount
    returned by Tenderly (`amount_out_yes_wei` or `amount_out_no_wei`).
    """

    label_kind_lc = label_kind.lower()
    fixed_kind_lc = fixed_kind.lower()

    def _handler(state, sim):
        label = f"SwapR {label_kind.upper()} (exact-{fixed_kind_lc})"
        # Re-use existing pretty-printer util
        parse_swapr_results([sim], label=label, fixed=fixed_kind_lc)

        returned_amount_wei = extract_return(sim, None, fixed_kind_lc)
        if returned_amount_wei is not None:
            if label_kind_lc == "yes":
                state["amount_out_yes_wei"] = returned_amount_wei
            else:
                state["amount_out_no_wei"] = returned_amount_wei
        return state

    return _handler

def extract_return(sim, amount_in_or_out_wei_local, fixed_kind):
    tx = sim.get("transaction", {})
    call_trace = tx.get("transaction_info", {}).get("call_trace", {})
    output_hex = call_trace.get("output")
    if output_hex and output_hex != "0x":
        try:
            returned_amount_wei = int(output_hex[2:], 16)
        except ValueError:
            return None
        return returned_amount_wei
    return None

def get_gno_yes_and_no_amounts_from_sdai(amount, gno_amount=None, liquidate_conditional_sdai_amount=None, price=100):
    split_amount_in_wei = w3.to_wei(Decimal(amount), "ether")
    if gno_amount is not None:
        gno_amount_in_wei = w3.to_wei(Decimal(gno_amount), "ether")
    else:
        gno_amount_in_wei = None

    split_tx = build_split_tx(
        w3,
        client,
        router_addr,
        proposal_addr,
        collateral_addr,
        split_amount_in_wei,
        acct.address,
    )

    steps = []
    steps.append((split_tx, handle_split))

    swap_steps = build_step_1_swap_steps(split_amount_in_wei, gno_amount_in_wei, price)
    steps.extend(swap_steps)

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
    if liquidate_conditional_sdai_amount:
        steps += add_conditional_sdai_liquidation_steps(
            liquidate_conditional_sdai_amount,
            handle_liquidate,
            handle_buy_sdai_yes,
            handle_merge_conditional_sdai,
    )

    gno_to_sdai_txs = []
    if gno_amount_in_wei:
        print("Sell GNO to sDAI, gno_amount_in_wei:", gno_amount_in_wei)
        gno_to_sdai_txs.append(
            build_sell_gno_to_sdai_swap_tx(
                w3,
                client,
                gno_amount_in_wei,
                1,
                acct.address,
            )
        )
    if gno_to_sdai_txs:
        steps.append((gno_to_sdai_txs[0], handle_balancer))

    bundle = [tx for tx, _ in steps]
    print("--- Prepared Bundle ---")
    print(bundle)
    result = client.simulate(bundle)
    state = {
        "amount_out_yes_wei": None,
        "amount_out_no_wei": None,
        "sdai_out": Decimal("0"),
    }
    if result and result.get("simulation_results"):
        sims = result["simulation_results"]
        for idx, sim in enumerate(sims):
            if sim.get("error"):
                print(sim["error"])
                continue
            tx = sim.get("transaction", {})
            if not tx:
                print("No transaction data in result.")
                continue
            if tx.get("status") is False:
                print("Transaction REVERTED.")
                continue
            print("Swap transaction did NOT revert.")
            if idx < len(steps):
                _, handler = steps[idx]
                state = handler(state, sim)
            else:
                print("No handler defined for this tx.")
    else:
        print("Simulation failed or returned no results.")
    sdai_in = Decimal(amount) + Decimal(max(-(liquidate_conditional_sdai_amount or 0), 0))
    return {
        "amount_out_yes": w3.from_wei(state["amount_out_yes_wei"], "ether") if state["amount_out_yes_wei"] else None,
        "amount_out_no" : w3.from_wei(state["amount_out_no_wei"], "ether") if state["amount_out_no_wei"]  else None,
        "sdai_in" : sdai_in,
        "sdai_out": state["sdai_out"],
        "sdai_net": state["sdai_out"] - sdai_in,
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print(
            "Usage: python -m futarchy.experimental.exchanges.simulator.simulator <amount> [<gno_amount>] [<liquidate_conditional_sdai_amount>]"
        )
        sys.exit(1)
    amount = float(sys.argv[1])
    gno_amount = float(sys.argv[2]) if len(sys.argv) > 2 else None
    liquidate_conditional_sdai_amount = float(sys.argv[3]) if len(sys.argv) > 3 else None
    result = get_gno_yes_and_no_amounts_from_sdai(amount, gno_amount, liquidate_conditional_sdai_amount)
    print(
        "(amount_out_yes = {}   , amount_out_no = {}   , sdai_in = {}   , sdai_out = {}   , sdai_net = {})".format(
            result["amount_out_yes"],
            result["amount_out_no"],
            result["sdai_in"],
            result["sdai_out"],
            result["sdai_net"],
        ),
    )
# python -m futarchy.experimental.exchanges.simulator.simulator <amount> [<gno_amount>] [<liquidate_conditional_sdai_amount>]
